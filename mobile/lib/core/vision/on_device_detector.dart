/// What the on-device model thinks the photo shows.
class OnDeviceGuess {
  const OnDeviceGuess({required this.cropId, required this.confidence});

  /// Crop id as used by the API (`apple`, `tomato`, ...).
  final String cropId;

  /// 0 to 1.
  final double confidence;
}

/// A small offline crop identifier that runs before the upload; its answer is sent to the server as
/// `client_crop` / `client_confidence` (a hint only: the server decides).
///
/// NOT AVAILABLE YET. The planned model is `neghani/plantvillage-mobilenetv2` (Apache-2.0, 38 classes, about
/// 3 MB as int8 TFLite) run with `flutter_litert` or `tflite_flutter`. It has not been converted, and the field
/// test of 19 Oct 2026 showed it is unreliable on real leaves (0 of 23 over all classes), so even when it
/// ships its answer must stay a hint. Until then [StubOnDeviceDetector] returns null and nothing is sent.
abstract interface class OnDeviceDetector {
  /// Null when there is no model or no confident answer.
  Future<OnDeviceGuess?> detect(String imagePath);
}

class StubOnDeviceDetector implements OnDeviceDetector {
  const StubOnDeviceDetector();

  @override
  Future<OnDeviceGuess?> detect(String imagePath) async => null;
}
