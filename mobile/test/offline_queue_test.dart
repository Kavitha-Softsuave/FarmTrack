import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/offline/offline_queue.dart';
import 'package:farmtrack/core/offline/persistent_offline_queue.dart';

import 'offline_support.dart';

void main() {
  late QueueRig rig;

  setUp(() => rig = QueueRig());
  tearDown(() => rig.dispose());

  group('queued while offline, sent after reconnect', () {
    test('a scan waits offline, is sent once when the network is back, and its files are removed', () async {
      final queue = rig.make();
      final watch = QueueWatcher(queue);
      final photos = rig.photos(2);
      rig.api.failWith(const ApiException.network(), ops: {'createScan'});

      final key = await queue.enqueueScan(
        photoPaths: photos,
        clientCrop: 'apple',
        clientConfidence: 0.7,
        takenAt: DateTime.utc(2026, 5, 12, 7, 30),
      );
      expect(queue.pending, 1);
      expect(rig.filesOnDisk, unorderedEquals(['$key.json', key]));

      await queue.flush();
      expect(queue.pending, 1, reason: 'still no network: nothing is lost');
      expect(rig.api.calls.where((c) => c == 'createScan'), hasLength(1));
      expect(rig.api.scans, isEmpty);

      rig.api.clearFailure();
      await queue.flush();
      await watch.settle();

      expect(queue.pending, 0);
      expect(rig.api.scans, hasLength(1), reason: 'sent exactly once');
      expect(rig.api.uploadedPhotoPaths.single, hasLength(2));
      expect(rig.filesOnDisk, isEmpty, reason: 'the item and its photo copies are deleted after the send');
      expect(rig.api.lastClientGuess, (crop: 'apple', confidence: 0.7));
      final sent = watch.of(QueueEventType.sent).single;
      expect(sent.kind, QueueKind.scan);
      expect(sent.key, key);
      expect(sent.scan!.id, rig.api.scans.keys.single, reason: 'the server answer travels in the event');
      expect(watch.counts, containsAllInOrder([1, 0]));
      await watch.close();
    });

    test('the photos are copied: the camera cache can be cleared while the item waits', () async {
      final queue = rig.make();
      final photos = rig.photos(1, bytes: 300);
      rig.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: photos);
      File(photos.single).deleteSync();
      rig.cameraDir.deleteSync(recursive: true);

      rig.api.clearFailure();
      await queue.flush();
      expect(rig.api.scans, hasLength(1));
      expect(File(rig.api.uploadedPhotoPaths.single.single).path, contains('pending'));
    });

    test('every attempt sends the same idempotency key, and it is the key enqueue returned', () async {
      final api = LossyApi();
      final keyed = QueueRig(api: api);
      addTearDown(keyed.dispose);
      final queue = keyed.make();
      api.failWith(const ApiException.network(), ops: {'createScan'}, times: 3);
      final key = await queue.enqueueScan(photoPaths: keyed.photos(1));
      for (var i = 0; i < 4; i++) {
        await queue.flush(); // three failures, then it goes through
      }
      expect(api.attemptedKeys, [key, key, key, key]);
      expect(api.scans, hasLength(1));
      expect(key, matches(RegExp(r'^[0-9a-f]{32}$')));
    });

    test('a lost answer never makes a duplicate: the retry gets the stored answer of the first request', () async {
      final api = LossyApi();
      final lossy = QueueRig(api: api);
      addTearDown(lossy.dispose);
      final queue = lossy.make();
      final watch = QueueWatcher(queue);
      api.loseAnswers = 1;
      await queue.enqueueScan(photoPaths: lossy.photos(1));

      await queue.flush(); // the server stored the scan, the answer was lost
      expect(queue.pending, 1);
      expect(api.scans, hasLength(1));

      await queue.flush(); // same key again
      await watch.settle();
      expect(queue.pending, 0);
      expect(api.scans, hasLength(1), reason: 'no second scan');
      expect(api.uploadedPhotoPaths, hasLength(1), reason: 'the server did not process the photos twice');
      expect(api.idempotencyKeys.toSet(), hasLength(1));
      expect(watch.of(QueueEventType.sent).single.scan!.id, api.scans.keys.single);
      await watch.close();
    });

    test('a key used by a live attempt can be reused by the queue (KeyedOfflineQueue)', () async {
      final api = LossyApi();
      final lossy = QueueRig(api: api);
      addTearDown(lossy.dispose);
      final queue = lossy.make();
      api.loseAnswers = 1;
      final photos = lossy.photos(1);
      const live = 'abcdef0123456789abcdef0123456789';
      // The screen's own attempt: processed by the server, answer lost.
      await expectLater(api.createScan(photoPaths: photos, idempotencyKey: live), throwsA(isA<ApiException>()));
      await queue.enqueueScanWithKey(live, photoPaths: photos);
      await queue.flush();
      expect(api.scans, hasLength(1), reason: 'the queued retry did not create a second scan');
      expect(queue.pending, 0);
    });

    test('enqueueing the same key twice keeps one item', () async {
      final queue = rig.make();
      const key = 'abcdef0123456789abcdef0123456789';
      final photos = rig.photos(1);
      await queue.enqueueScanWithKey(key, photoPaths: photos);
      await queue.enqueueScanWithKey(key, photoPaths: photos);
      expect(queue.pending, 1);
    });

    test('a key that is not a safe file name is refused', () async {
      final queue = rig.make();
      await expectLater(queue.enqueueScanWithKey('../../x', photoPaths: rig.photos(1)), throwsArgumentError);
      await expectLater(queue.enqueueScanWithKey('short', photoPaths: rig.photos(1)), throwsArgumentError);
    });
  });

  group('order and rounds', () {
    test('items are sent sequentially, oldest first', () async {
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      final a = await queue.enqueueScan(photoPaths: rig.photos(1));
      rig.clock.advance(const Duration(minutes: 1));
      final b = await queue.enqueueScan(photoPaths: rig.photos(1));
      rig.clock.advance(const Duration(minutes: 1));
      final c = await queue.enqueueSprayLog(const SprayLogIn(cropId: 'apple', freeText: 'x'));
      expect(queue.keys, [a, b, c]);
      rig.api.clearFailure();
      rig.api.idempotencyKeys.clear();

      await queue.flush();
      expect(rig.api.idempotencyKeys, [a, b, c]);
      expect(queue.pending, 0);
    });

    test('a connection problem stops the round: the other items are not even tried', () async {
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      for (var i = 0; i < 3; i++) {
        await queue.enqueueScan(photoPaths: rig.photos(1));
        rig.clock.advance(const Duration(seconds: 1));
      }
      rig.api.calls.clear();
      await queue.flush();
      expect(rig.api.calls, ['createScan']);
      expect(queue.pending, 3);
    });

    test('two flushes at the same time make one round', () async {
      final queue = rig.make();
      await queue.enqueueScan(photoPaths: rig.photos(1));
      await Future.wait([queue.flush(), queue.flush(), queue.flush()]);
      expect(rig.api.calls.where((c) => c == 'createScan'), hasLength(1));
      expect(rig.api.scans, hasLength(1));
    });

    test('a spray log is sent with its key and the answer is reported', () async {
      final queue = rig.make();
      final watch = QueueWatcher(queue);
      rig.api.failWith(const ApiException.network());
      final key = await queue.enqueueSprayLog(
        SprayLogIn(
          cropId: 'apple',
          productId: 'P007',
          adviceId: 'adv-1',
          sprayedAt: DateTime.utc(2026, 5, 11, 9),
          notes: 'morning',
        ),
      );
      await queue.flush();
      expect(queue.pending, 1);
      rig.api.clearFailure();
      await queue.flush();
      await watch.settle();
      expect(rig.api.sprayLogsIn.single.productId, 'P007');
      expect(rig.api.sprayLogsIn.single.notes, 'morning');
      expect(rig.api.sprayLogsIn.single.sprayedAt, DateTime.utc(2026, 5, 11, 9));
      expect(rig.api.idempotencyKeys.toSet(), {key});
      final sent = watch.of(QueueEventType.sent).single;
      expect(sent.kind, QueueKind.sprayLog);
      expect(sent.sprayLog!.id, startsWith('log-'));
      expect(rig.filesOnDisk, isEmpty);
      await watch.close();
    });
  });

  group('which errors are retried', () {
    test('a 4xx drops the item, deletes its files and tells the app once', () async {
      final queue = rig.make();
      final watch = QueueWatcher(queue);
      rig.api.failWith(unprocessable, ops: {'createScan'});
      final key = await queue.enqueueScan(photoPaths: rig.photos(1));
      await queue.flush();
      await watch.settle();
      expect(queue.pending, 0);
      expect(rig.filesOnDisk, isEmpty);
      final dropped = watch.of(QueueEventType.dropped).single;
      expect(dropped.key, key);
      expect(dropped.kind, QueueKind.scan);
      expect((dropped.error! as ApiException).statusCode, 422);
      expect(rig.api.calls.where((c) => c == 'createScan'), hasLength(1), reason: 'never retried');
      await watch.close();
    });

    test('a 404 on a spray log is dropped as well', () async {
      final queue = rig.make();
      final watch = QueueWatcher(queue);
      rig.api.failWith(
        const ApiException(kind: ApiErrorKind.client, code: 'not_found', statusCode: 404),
        ops: {'createSprayLog'},
      );
      await queue.enqueueSprayLog(const SprayLogIn(cropId: 'apple', freeText: 'x'));
      await queue.flush();
      await watch.settle();
      expect(queue.pending, 0);
      expect(watch.of(QueueEventType.dropped), hasLength(1));
      await watch.close();
    });

    test('5xx, 401 and 429 keep the item; a timeout counts as no connection', () async {
      final queue = rig.make();
      final watch = QueueWatcher(queue);
      await queue.enqueueScan(photoPaths: rig.photos(1));
      for (final error in [serverError, notAuthenticated, tooManyRequests, const ApiException.timeout()]) {
        rig.api.failWith(error, ops: {'createScan'});
        await queue.flush();
        expect(queue.pending, 1, reason: '$error must not lose the item');
      }
      await watch.settle();
      expect(watch.events, isEmpty, reason: 'nothing was sent or dropped');
      rig.api.clearFailure();
      await queue.flush();
      expect(queue.pending, 0);
      await watch.close();
    });

    test('a 5xx on one item does not block the items behind it', () async {
      final queue = rig.make();
      final first = await queue.enqueueScan(photoPaths: rig.photos(1));
      rig.clock.advance(const Duration(seconds: 1));
      await queue.enqueueSprayLog(const SprayLogIn(cropId: 'apple', freeText: 'x'));
      rig.api.failWith(serverError, ops: {'createScan'});
      await queue.flush();
      expect(queue.keys, [first], reason: 'the diary entry went through, the scan waits');
    });

    test('flush never throws, even when the API throws something unexpected', () async {
      final odd = QueueRig(api: _ThrowingApi());
      addTearDown(odd.dispose);
      final queue = odd.make();
      await queue.enqueueScan(photoPaths: odd.photos(1));
      await queue.flush();
      expect(queue.pending, 1);
      expect(odd.clock.activeTimers, 1, reason: 'it will try again later');
    });

    test('a photo that is gone when the item is sent drops it', () async {
      final queue = rig.make();
      final watch = QueueWatcher(queue);
      final key = await queue.enqueueScan(photoPaths: rig.photos(1));
      final copy = Directory('${rig.queueDir.path}${Platform.pathSeparator}$key').listSync().single;
      copy.deleteSync();
      await queue.flush();
      await watch.settle();
      expect(queue.pending, 0);
      expect(
        (watch.of(QueueEventType.dropped).single.error! as OfflineQueueException).reason,
        OfflineRejectReason.photoMissing,
      );
      expect(rig.api.calls.where((c) => c == 'createScan'), isEmpty);
      await watch.close();
    });
  });

  group('timer with back-off', () {
    test('30 s, then twice as long after every failed round, up to 15 minutes', () async {
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: rig.photos(1));
      expect(rig.clock.armedFor, const Duration(seconds: 30));

      for (var i = 0; i < 9; i++) {
        rig.clock.advance(rig.clock.armedFor!);
        await queue.flush(); // joins the round the timer started
      }
      expect(rig.clock.scheduled, [
        const Duration(seconds: 30),
        const Duration(seconds: 60),
        const Duration(minutes: 2),
        const Duration(minutes: 4),
        const Duration(minutes: 8),
        const Duration(minutes: 15),
        const Duration(minutes: 15),
        const Duration(minutes: 15),
        const Duration(minutes: 15),
        const Duration(minutes: 15),
      ]);
      expect(rig.clock.activeTimers, 1);
    });

    test('the timer sends the item when the network comes back, and then stops', () async {
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: rig.photos(1));
      rig.clock.advance(const Duration(seconds: 30));
      await queue.flush();
      expect(queue.pending, 1);
      rig.api.clearFailure();
      rig.clock.advance(const Duration(seconds: 60));
      await queue.flush();
      expect(queue.pending, 0);
      expect(rig.clock.activeTimers, 0, reason: 'nothing left to retry');
    });

    test('after a success the next wait starts at 30 s again', () async {
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: rig.photos(1));
      rig.clock.advance(const Duration(seconds: 30));
      await queue.flush();
      rig.clock.advance(const Duration(seconds: 60));
      await queue.flush();
      rig.api.clearFailure();
      rig.clock.advance(const Duration(minutes: 2));
      await queue.flush();
      expect(queue.pending, 0);
      rig.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: rig.photos(1));
      expect(rig.clock.armedFor, const Duration(seconds: 30));
    });

    test('in the background the timer is off; flush() works at any time', () async {
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: rig.photos(1));
      expect(rig.clock.activeTimers, 1);
      queue.foreground = false;
      expect(rig.clock.activeTimers, 0);
      await queue.flush();
      expect(rig.clock.activeTimers, 0, reason: 'a background round does not arm the timer');
      queue.foreground = true;
      await queue.flush();
      expect(rig.clock.activeTimers, 1);
    });
  });

  group('restart', () {
    test('items and photos survive a restart and are sent by the new queue', () async {
      final first = rig.make();
      rig.api.failWith(const ApiException.network());
      final a = await first.enqueueScan(photoPaths: rig.photos(2), clientCrop: 'apple', clientConfidence: 0.4);
      rig.clock.advance(const Duration(minutes: 5));
      final b = await first.enqueueSprayLog(const SprayLogIn(cropId: 'potato', freeText: 'copper'));
      first.dispose();
      rig.cameraDir.deleteSync(recursive: true);

      final second = rig.make();
      expect(second.pending, 2);
      expect(second.keys, [a, b]);
      expect(second.usedBytes, greaterThan(100));
      rig.api.clearFailure();
      await second.flush();
      expect(second.pending, 0);
      expect(rig.api.idempotencyKeys, [a, b], reason: 'the keys survived the restart');
      expect(rig.api.lastClientGuess, (crop: 'apple', confidence: 0.4));
      expect(rig.api.sprayLogsIn.single.freeText, 'copper');
      expect(rig.filesOnDisk, isEmpty);
    });

    test('the retry timer is armed again after a restart once a round fails', () async {
      final first = rig.make();
      rig.api.failWith(const ApiException.network());
      await first.enqueueScan(photoPaths: rig.photos(1));
      first.dispose();
      final second = rig.make();
      await second.flush();
      expect(rig.clock.activeTimers, 1);
    });

    test('damaged files are deleted and the good ones still load', () async {
      final first = rig.make();
      rig.api.failWith(const ApiException.network());
      final good = await first.enqueueScan(photoPaths: rig.photos(1));
      rig.clock.advance(const Duration(seconds: 1));
      final noPhotos = await first.enqueueScan(photoPaths: rig.photos(1));
      first.dispose();
      String path(String name) => '${rig.queueDir.path}${Platform.pathSeparator}$name';

      File(path('not_json_at_all.json')).writeAsStringSync('{{{ this is not json');
      File(path('0123456789abcdef.json')).writeAsStringSync(jsonEncode({'key': 'other_key_here_1', 'kind': 'scan'}));
      File(path('aaaaaaaaaaaaaaaa.json'))
          .writeAsStringSync(jsonEncode({'key': 'aaaaaaaaaaaaaaaa', 'kind': 'teleport'}));
      File(path('left_over.json.tmp')).writeAsStringSync('half a write');
      Directory(path('orphan_photos_dir')).createSync();
      File(path('orphan_photos_dir${Platform.pathSeparator}p0.jpg')).writeAsBytesSync([1, 2, 3]);
      Directory(path(noPhotos)).deleteSync(recursive: true);

      final second = rig.make();
      expect(second.keys, [good]);
      expect(rig.filesOnDisk, unorderedEquals(['$good.json', good]));
    });
  });

  group('limits', () {
    test('the 21st item is refused with a clear exception and leaves nothing behind', () async {
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      for (var i = 0; i < 20; i++) {
        await queue.enqueueSprayLog(SprayLogIn(cropId: 'apple', freeText: 'item $i'));
      }
      expect(queue.pending, 20);
      final photos = rig.photos(1);
      await expectLater(
        queue.enqueueScan(photoPaths: photos),
        throwsA(isA<OfflineQueueException>().having((e) => e.reason, 'reason', OfflineRejectReason.tooManyItems)),
      );
      expect(queue.pending, 20);
      expect(rig.filesOnDisk, hasLength(20), reason: 'no half-written item');
      expect(File(photos.single).existsSync(), isTrue, reason: 'the camera photo is untouched');
    });

    test('a scan that would pass the size limit is refused; smaller ones still fit', () async {
      final small = QueueRig(limits: const OfflineQueueLimits(maxBytes: 2000));
      addTearDown(small.dispose);
      final queue = small.make();
      small.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: small.photos(2, bytes: 600)); // about 1,200 bytes plus the json
      await expectLater(
        queue.enqueueScan(photoPaths: small.photos(2, bytes: 600)),
        throwsA(isA<OfflineQueueException>().having((e) => e.reason, 'reason', OfflineRejectReason.tooMuchData)),
      );
      expect(queue.pending, 1);
      expect(small.filesOnDisk, hasLength(2));
      await queue.enqueueScan(photoPaths: small.photos(1, bytes: 50));
      expect(queue.pending, 2);
    });

    test('the default size limit is about 100 MB and 20 items', () {
      const limits = OfflineQueueLimits();
      expect(limits.maxBytes, 100 * 1024 * 1024);
      expect(limits.maxItems, 20);
      expect(limits.maxAge, const Duration(days: 7));
    });

    test('a photo that does not exist and an empty photo list are refused', () async {
      final queue = rig.make();
      await expectLater(
        queue.enqueueScan(photoPaths: ['${rig.cameraDir.path}/nothing.jpg']),
        throwsA(isA<OfflineQueueException>().having((e) => e.reason, 'reason', OfflineRejectReason.photoMissing)),
      );
      await expectLater(
        queue.enqueueScan(photoPaths: const []),
        throwsA(isA<OfflineQueueException>().having((e) => e.reason, 'reason', OfflineRejectReason.noPhotos)),
      );
      expect(rig.filesOnDisk, isEmpty);
    });

    test('items older than seven days are dropped, younger ones are kept', () async {
      final queue = rig.make();
      final watch = QueueWatcher(queue);
      rig.api.failWith(const ApiException.network());
      final old = await queue.enqueueScan(photoPaths: rig.photos(1));
      rig.clock.advance(const Duration(days: 3));
      final young = await queue.enqueueSprayLog(const SprayLogIn(cropId: 'apple', freeText: 'x'));

      rig.clock.advance(const Duration(days: 4, minutes: -1)); // the first is 6 d 23 h 59 min old
      await queue.flush();
      expect(queue.keys, [old, young]);

      rig.clock.advance(const Duration(minutes: 2)); // now it is older than seven days
      await queue.flush();
      await watch.settle();
      expect(queue.keys, [young]);
      final dropped = watch.of(QueueEventType.dropped).single;
      expect(dropped.key, old);
      expect((dropped.error! as OfflineQueueException).reason, OfflineRejectReason.expired);
      expect(rig.filesOnDisk, ['$young.json'], reason: 'the old photos are gone too');
      await watch.close();
    });

    test('items that expired while the app was closed are dropped at the next start', () async {
      final first = rig.make();
      rig.api.failWith(const ApiException.network());
      await first.enqueueScan(photoPaths: rig.photos(1));
      first.dispose();
      rig.clock.advance(const Duration(days: 8));
      final second = rig.make();
      expect(second.pending, 0);
      expect(rig.filesOnDisk, isEmpty);
    });
  });

  group('shared phone', () {
    test('an item waits for its owner: another farmer logging in does not send it', () async {
      rig.farmer = 'F001';
      final queue = rig.make();
      rig.api.failWith(const ApiException.network());
      await queue.enqueueScan(photoPaths: rig.photos(1));
      rig.api.clearFailure();

      rig.farmer = 'F002';
      await queue.flush();
      expect(queue.pending, 1);
      expect(rig.api.scans, isEmpty);
      expect(rig.clock.activeTimers, 0, reason: 'nothing to retry for farmer F002: no timer');

      rig.farmer = 'F001';
      await queue.flush();
      expect(queue.pending, 0);
      expect(rig.api.scans, hasLength(1));
    });
  });

  test('nothing is sent while nobody is logged in; the next flush after the login sends', () async {
    final queue = rig.make();
    rig.api.failWith(const ApiException.network());
    await queue.enqueueScan(photoPaths: rig.photos(1));
    rig.api.clearFailure();
    rig.api.calls.clear();

    rig.signedIn = false;
    await queue.flush();
    expect(rig.api.calls, isEmpty, reason: 'no request without a login');
    expect(queue.pending, 1);
    expect(rig.clock.activeTimers, 0, reason: 'the login triggers the next flush, no timer spins meanwhile');

    rig.signedIn = true;
    await queue.flush();
    expect(queue.pending, 0);
    expect(rig.api.scans, hasLength(1));
  });

  test('the queue folder is created when it does not exist', () {
    expect(rig.queueDir.existsSync(), isFalse);
    expect(rig.make().pending, 0);
    expect(rig.queueDir.existsSync(), isTrue);
  });

  test('InMemoryOfflineQueue (kept for tests) still implements the frozen interface', () async {
    final q = InMemoryOfflineQueue();
    await q.enqueueSprayLog(const SprayLogIn(cropId: 'apple'));
    expect(q.pending, 1);
  });
}

class _ThrowingApi extends MockApiClient {
  _ThrowingApi() : super(latency: Duration.zero);

  @override
  Future<ScanOut> createScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
    String? idempotencyKey,
    UploadProgressCallback? onProgress,
    CancelHandle? cancel,
  }) async => throw StateError('something nobody expected');
}
