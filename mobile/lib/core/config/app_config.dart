import 'dart:io' show Platform;

/// Build-time configuration, set with `--dart-define=NAME=value`.
class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    required this.useMockApi,
    this.maxPhotos = 4,
    this.mockLatency = const Duration(milliseconds: 500),
  });

  /// Reads the `--dart-define` values. The mock API is the default in tests (`flutter test` sets FLUTTER_TEST).
  factory AppConfig.fromEnvironment() {
    const baseUrl = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000');
    const mock = bool.fromEnvironment('USE_MOCK_API', defaultValue: false);
    final underTest = Platform.environment.containsKey('FLUTTER_TEST');
    return AppConfig(apiBaseUrl: baseUrl, useMockApi: mock || underTest);
  }

  /// Zero latency, mock API: what widget tests use.
  const AppConfig.test()
    : apiBaseUrl = 'http://test.invalid',
      useMockApi = true,
      maxPhotos = 4,
      mockLatency = Duration.zero;

  final String apiBaseUrl;
  final bool useMockApi;

  /// The backend accepts 1 to 4 photos per scan (`max_photos_per_scan`).
  final int maxPhotos;
  final Duration mockLatency;
}
