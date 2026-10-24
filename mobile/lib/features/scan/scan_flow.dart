import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/network/api_client.dart';
import '../../core/errors/api_exception.dart';
import '../../core/offline/offline_queue.dart';
import '../../core/offline/persistent_offline_queue.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../offline/last_result.dart';

/// [queued]: the phone had no connection, so the photos were saved to be sent later (the "saved" screen follows).
enum ScanPhase { idle, uploading, analysing, done, failed, queued }

class ScanFlowState {
  const ScanFlowState({
    this.photos = const [],
    this.phase = ScanPhase.idle,
    this.progress = 0,
    this.scan,
    this.error,
    this.added = 0,
  });

  /// Paths of the photos to send (at most [AppConfig.maxPhotos]).
  final List<String> photos;
  final ScanPhase phase;

  /// Upload progress, 0 to 1.
  final double progress;

  /// The latest answer of the server for this scan.
  final ScanOut? scan;
  final Object? error;

  /// Counts photos added in this flow; the review screen speaks "photo taken" when it grows.
  final int added;

  ScanFlowState copyWith({
    List<String>? photos,
    ScanPhase? phase,
    double? progress,
    Object? scan = _keep,
    Object? error = _keep,
    int? added,
  }) => ScanFlowState(
    photos: photos ?? this.photos,
    phase: phase ?? this.phase,
    progress: progress ?? this.progress,
    scan: identical(scan, _keep) ? this.scan : scan as ScanOut?,
    error: identical(error, _keep) ? this.error : error,
    added: added ?? this.added,
  );

  static const Object _keep = Object();
}

/// Where each scan answer goes. The server's status decides the screen.
String routeForScan(ScanOut scan) => switch (scan.status) {
  ScanStatus.ok => Routes.scanAdvice,
  ScanStatus.confirmCrop => scan.crop?.isKnown ?? false ? Routes.scanConfirm : Routes.scanCrops,
  ScanStatus.photoUnusable => Routes.scanRetake,
  ScanStatus.needsExpert || ScanStatus.noApprovedData || ScanStatus.notADisease => Routes.scanExpert,
};

final scanFlowProvider = NotifierProvider<ScanFlowNotifier, ScanFlowState>(ScanFlowNotifier.new);

/// The state of one scan: the photos taken, the upload, and the server's answer.
///
/// A connection failure saves the photos in the offline queue and ends in [ScanPhase.queued] (the queue sends them
/// when the phone is online again). If even that is refused (queue full, photo gone) the phase is [ScanPhase.failed]
/// with the queue's exception, which the error screen turns into `error_try_again`.
class ScanFlowNotifier extends Notifier<ScanFlowState> {
  CancelHandle? _cancel;
  int _run = 0;
  int _announced = 0;

  /// One idempotency key for the photos of this scan: the live attempt, the retry button and the offline queue all
  /// send the same one, so a request that reached the server but lost its answer never makes a second scan.
  String? _uploadKey;

  @override
  ScanFlowState build() => const ScanFlowState();

  int get maxPhotos => ref.read(appConfigProvider).maxPhotos;

  /// Starts over (new scan, no photos).
  void reset() {
    _cancelRunning();
    _announced = 0;
    _uploadKey = null;
    state = const ScanFlowState();
  }

  /// Opens a result that did not come from this flow (a queued scan that was sent): the result screens read it.
  ///
  /// [remember] false when the result is the one already kept as "last advice" (opening it again must not make it newer).
  void showResult(ScanOut scan, {bool remember = true}) {
    _cancelRunning();
    _announced = 0;
    _uploadKey = null;
    state = ScanFlowState(phase: ScanPhase.done, progress: 1, scan: scan);
    if (remember) _remember(scan);
  }

  /// Keeps a finished answer on the phone, so the last advice can be read again with no internet.
  void _remember(ScanOut scan) => unawaited(ref.read(lastResultProvider.notifier).remember(scan));

  /// True when a photo was added that the review screen has not yet announced ("Photo taken").
  bool get hasUnannouncedPhoto => state.added > _announced;

  void markAnnounced() => _announced = state.added;

  /// Returns false when the limit is reached.
  bool addPhoto(String path) {
    if (state.photos.length >= maxPhotos) return false;
    _uploadKey = null; // other photos: another request
    state = state.copyWith(photos: [...state.photos, path], added: state.added + 1);
    return true;
  }

  void removePhotoAt(int index) {
    if (index < 0 || index >= state.photos.length) return;
    _uploadKey = null;
    state = state.copyWith(photos: [...state.photos]..removeAt(index));
  }

  void _cancelRunning() {
    _run++;
    _cancel?.cancel();
    _cancel = null;
  }

  /// The farmer pressed the cancel cross (or the back button) while sending.
  void cancel() {
    _cancelRunning();
    state = state.copyWith(phase: ScanPhase.idle, progress: 0, error: null);
  }

  /// Uploads the photos. Returns the answer, or null on failure, cancel or when the photos were saved for later
  /// (see [ScanFlowState.phase] and [ScanFlowState.error]).
  Future<ScanOut?> submit() async {
    if (state.photos.isEmpty) return null;
    final cancel = CancelHandle();
    _cancel = cancel;
    final run = ++_run;
    final photos = List<String>.of(state.photos);
    final key = _uploadKey ??= newIdempotencyKey();
    final takenAt = DateTime.now();
    state = state.copyWith(phase: ScanPhase.uploading, progress: 0, error: null, scan: null);
    (String, double)? guess;
    try {
      guess = await _guess(photos.first);
      final scan = await ref
          .read(apiClientProvider)
          .createScan(
            photoPaths: photos,
            clientCrop: guess?.$1,
            clientConfidence: guess?.$2,
            takenAt: takenAt,
            idempotencyKey: key,
            cancel: cancel,
            onProgress: (sent, total) {
              if (run != _run || total <= 0) return;
              final done = sent >= total;
              state = state.copyWith(progress: sent / total, phase: done ? ScanPhase.analysing : ScanPhase.uploading);
            },
          );
      if (run != _run) return null;
      _uploadKey = null;
      state = state.copyWith(phase: ScanPhase.done, progress: 1, scan: scan);
      _remember(scan);
      return scan;
    } on ApiException catch (e) {
      if (run != _run) return null;
      if (e.isCancelled) {
        state = state.copyWith(phase: ScanPhase.idle);
      } else if (e.isConnectionProblem) {
        await _saveForLater(run, key, photos, guess, takenAt);
      } else {
        state = state.copyWith(phase: ScanPhase.failed, error: e);
      }
      return null;
    } on Object catch (e) {
      // For example a photo file that is gone: show the error screen instead of waiting for ever.
      if (run != _run) return null;
      state = state.copyWith(phase: ScanPhase.failed, error: e);
      return null;
    }
  }

  /// No connection: keep the photos in the offline queue (with the key of the live attempt) and say so.
  Future<void> _saveForLater(
    int run,
    String key,
    List<String> photos,
    (String, double)? guess,
    DateTime takenAt,
  ) async {
    try {
      final queue = ref.read(offlineQueueProvider);
      if (queue is KeyedOfflineQueue) {
        await queue.enqueueScanWithKey(
          key,
          photoPaths: photos,
          clientCrop: guess?.$1,
          clientConfidence: guess?.$2,
          takenAt: takenAt,
        );
      } else {
        await queue.enqueueScan(
          photoPaths: photos,
          clientCrop: guess?.$1,
          clientConfidence: guess?.$2,
          takenAt: takenAt,
        );
      }
      if (run != _run) return;
      _uploadKey = null;
      state = state.copyWith(phase: ScanPhase.queued, error: null);
    } on Object catch (e) {
      if (run != _run) return;
      state = state.copyWith(phase: ScanPhase.failed, error: e);
    }
  }

  /// The farmer ticked (or chose) a crop for the current scan.
  Future<ScanOut?> confirmCrop(String cropId) async {
    final scan = state.scan;
    if (scan == null) return null;
    final run = ++_run;
    state = state.copyWith(phase: ScanPhase.analysing, error: null);
    try {
      final next = await ref.read(apiClientProvider).confirmCrop(scan.id, cropId);
      if (run != _run) return null;
      state = state.copyWith(phase: ScanPhase.done, scan: next);
      _remember(next);
      return next;
    } on Object catch (e) {
      if (run != _run) return null;
      state = state.copyWith(phase: ScanPhase.failed, error: e);
      return null;
    }
  }

  /// What the on-device model thinks, if it has a model (it does not yet). A hint for the server only.
  Future<(String, double)?> _guess(String path) async {
    try {
      final g = await ref.read(onDeviceDetectorProvider).detect(path);
      return g == null ? null : (g.cropId, g.confidence);
    } catch (_) {
      return null;
    }
  }
}
