import 'json_utils.dart';
import 'localized.dart';

class AlertOut {
  const AlertOut({
    required this.id,
    this.kind = '',
    this.level = Severity.yellow,
    this.title = const LocalizedText(),
    this.body = const LocalizedText(),
    this.spoken = const SpokenOut(),
    this.createdAt,
    this.readAt,
    this.scanId,
  });

  factory AlertOut.fromJson(Json json) => AlertOut(
    id: json.str('id'),
    kind: json.str('kind'),
    level: Severity.parse(json['level']),
    title: LocalizedText.fromJson(json['title']),
    body: LocalizedText.fromJson(json['body']),
    spoken: SpokenOut.fromJson(json['spoken']),
    createdAt: json.dateOrNull('created_at'),
    readAt: json.dateOrNull('read_at'),
    scanId: json.strOrNull('scan_id'),
  );

  final String id;
  final String kind;
  final Severity level;
  final LocalizedText title;
  final LocalizedText body;
  final SpokenOut spoken;
  final DateTime? createdAt;
  final DateTime? readAt;

  /// The scan this alert is about (open `GET /v1/scans/{scan_id}`); null for alerts that are not about a photo.
  final String? scanId;

  bool get isRead => readAt != null;

  /// The same alert, marked as read at [at].
  AlertOut copyWithRead(DateTime at) => AlertOut(
    id: id,
    kind: kind,
    level: level,
    title: title,
    body: body,
    spoken: spoken,
    createdAt: createdAt,
    readAt: at,
    scanId: scanId,
  );

  Json toJson() => {
    'id': id,
    'kind': kind,
    'level': level.wire,
    'title': title.toJson(),
    'body': body.toJson(),
    'spoken': spoken.toJson(),
    'created_at': createdAt?.toIso8601String(),
    'read_at': readAt?.toIso8601String(),
    'scan_id': scanId,
  };
}

class AlertListOut {
  const AlertListOut({this.items = const [], this.unread = 0});

  factory AlertListOut.fromJson(Json json) =>
      AlertListOut(items: json.list('items', AlertOut.fromJson), unread: json.intOr('unread'));

  final List<AlertOut> items;
  final int unread;

  Json toJson() => {
    'items': [for (final a in items) a.toJson()],
    'unread': unread,
  };
}

class AskIn {
  const AskIn({required this.question, this.language = 'hi', this.cropId});

  final String question;
  final String language;
  final String? cropId;

  Json toJson() => compact({'question': question, 'language': language, 'crop_id': cropId});
}

class CitationOut {
  const CitationOut({required this.noteId, this.source = ''});

  factory CitationOut.fromJson(Json json) => CitationOut(noteId: json.str('note_id'), source: json.str('source'));

  final String noteId;
  final String source;

  Json toJson() => {'note_id': noteId, 'source': source};
}

class AskOut {
  const AskOut({this.answer = '', this.language = 'hi', this.refused = false, this.citations = const [], this.spoken});

  factory AskOut.fromJson(Json json) => AskOut(
    answer: json.str('answer'),
    language: json.str('language', 'hi'),
    refused: json.boolOr('refused'),
    citations: json.list('citations', CitationOut.fromJson),
    spoken: json['spoken'] is Map ? SpokenOut.fromJson(json['spoken']) : null,
  );

  final String answer;
  final String language;

  /// True when no approved note supports an answer: show [ask_no_answer] and offer the expert.
  final bool refused;
  final List<CitationOut> citations;
  final SpokenOut? spoken;

  Json toJson() => {
    'answer': answer,
    'language': language,
    'refused': refused,
    'citations': [for (final c in citations) c.toJson()],
    'spoken': spoken?.toJson(),
  };
}
