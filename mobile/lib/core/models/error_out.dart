import 'json_utils.dart';

/// The one error shape of the API: `{code, message, details}`.
class ErrorOut {
  const ErrorOut({required this.code, this.message = '', this.details});

  factory ErrorOut.fromJson(Json json) =>
      ErrorOut(code: json.str('code', 'unknown'), message: json.str('message'), details: json.objOrNull('details'));

  final String code;
  final String message;
  final Json? details;

  Json toJson() => compact({'code': code, 'message': message, 'details': details});
}
