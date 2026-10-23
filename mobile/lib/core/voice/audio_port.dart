import 'package:just_audio/just_audio.dart';

/// Plays recorded or generated mp3 files. Tests use a fake.
abstract interface class AudioPort {
  /// Plays a bundled asset; completes at the end of playback or when [stop] is called. Throws if it cannot play.
  Future<void> playAsset(String assetPath, {required double volume, required double speed});

  /// Plays a file on disk; same contract as [playAsset].
  Future<void> playFile(String path, {required double volume, required double speed});

  Future<void> stop();
}

/// `just_audio` (ExoPlayer on Android, AVPlayer on iOS). The player is created on first use.
class JustAudioPort implements AudioPort {
  AudioPlayer? _player;

  AudioPlayer get _p => _player ??= AudioPlayer();

  @override
  Future<void> playAsset(String assetPath, {required double volume, required double speed}) =>
      _play(() => _p.setAsset(assetPath), volume, speed);

  @override
  Future<void> playFile(String path, {required double volume, required double speed}) =>
      _play(() => _p.setFilePath(path), volume, speed);

  Future<void> _play(Future<Duration?> Function() load, double volume, double speed) async {
    final player = _p;
    await player.stop();
    await load();
    await player.setVolume(volume);
    await player.setSpeed(speed);
    await player.play();
  }

  @override
  Future<void> stop() async {
    final player = _player;
    if (player != null) await player.stop();
  }
}
