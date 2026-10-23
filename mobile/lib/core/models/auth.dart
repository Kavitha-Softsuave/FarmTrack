import 'json_utils.dart';

class FarmerOut {
  const FarmerOut({
    required this.id,
    this.name = '',
    this.phoneMasked = '',
    this.language = 'hi',
    this.district,
    this.village,
    this.crops = const [],
    this.primaryCrop,
    this.stationId,
  });

  factory FarmerOut.fromJson(Json json) => FarmerOut(
    id: json.str('id'),
    name: json.str('name'),
    phoneMasked: json.str('phone_masked'),
    language: json.str('language', 'hi'),
    district: json.strOrNull('district'),
    village: json.strOrNull('village'),
    crops: json.strList('crops'),
    primaryCrop: json.strOrNull('primary_crop'),
    stationId: json.strOrNull('station_id'),
  );

  final String id;
  final String name;
  final String phoneMasked;
  final String language;
  final String? district;
  final String? village;
  final List<String> crops;
  final String? primaryCrop;
  final String? stationId;

  Json toJson() => {
    'id': id,
    'name': name,
    'phone_masked': phoneMasked,
    'language': language,
    'district': district,
    'village': village,
    'crops': crops,
    'primary_crop': primaryCrop,
    'station_id': stationId,
  };
}

class FarmerPatch {
  const FarmerPatch({this.language, this.name});

  final String? language;
  final String? name;

  Json toJson() => compact({'language': language, 'name': name});
}

/// `POST /v1/auth/login`. The user name is lower-case and trimmed before it is sent.
class LoginIn {
  const LoginIn({required this.username, required this.password, this.deviceId});

  final String username;
  final String password;
  final String? deviceId;

  Json toJson() => compact({'username': username, 'password': password, 'device_id': deviceId});
}

class RefreshIn {
  const RefreshIn({required this.refreshToken});

  final String refreshToken;

  Json toJson() => {'refresh_token': refreshToken};
}

class TokenOut {
  const TokenOut({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'bearer',
    this.expiresIn = 0,
    required this.farmer,
  });

  factory TokenOut.fromJson(Json json) => TokenOut(
    accessToken: json.str('access_token'),
    refreshToken: json.str('refresh_token'),
    tokenType: json.str('token_type', 'bearer'),
    expiresIn: json.intOr('expires_in'),
    farmer: json.obj('farmer', FarmerOut.fromJson) ?? const FarmerOut(id: ''),
  );

  final String accessToken;
  final String refreshToken;
  final String tokenType;
  final int expiresIn;
  final FarmerOut farmer;

  Json toJson() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'token_type': tokenType,
    'expires_in': expiresIn,
    'farmer': farmer.toJson(),
  };
}

class DeviceIn {
  const DeviceIn({required this.platform, required this.pushToken, this.appVersion});

  /// `android` or `ios`.
  final String platform;
  final String pushToken;
  final String? appVersion;

  Json toJson() => compact({'platform': platform, 'push_token': pushToken, 'app_version': appVersion});
}
