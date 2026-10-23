import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';

/// The farmer's phone clock. Tests replace it; the diary says "today" and "yesterday" from it.
final clockProvider = Provider<DateTime Function()>((ref) => DateTime.now);

/// Day, month and number words of the current language. The lists come from `strings.json` (one comma separated
/// list per language), so a new language needs no code.
///
/// Digits may be written on the screen ([written]); the voice never gets digits ([spoken]).
class DateWords {
  DateWords(String Function(String key) t)
    : _months = _list(t('diary_month_words')),
      _numbers = _list(t('diary_number_words')),
      _weekdays = _list(t('diary_weekday_words')),
      _shortWeekdays = _list(t('field_weekday_short')),
      today = t('diary_today'),
      yesterday = t('diary_yesterday');

  final List<String> _months;
  final List<String> _numbers;
  final List<String> _weekdays;
  final List<String> _shortWeekdays;

  /// The words "Today" and "Yesterday" in this language.
  final String today;
  final String yesterday;

  static List<String> _list(String raw) => [for (final part in raw.split(',')) part.trim()];

  static String _at(List<String> list, int index, String fallback) =>
      index >= 0 && index < list.length && list[index].isNotEmpty ? list[index] : fallback;

  String month(int month) => _at(_months, month - 1, '');

  /// A number from 1 to 31 as a word.
  String number(int n) => _at(_numbers, n - 1, '$n');

  /// `DateTime.monday` is 1.
  String weekday(DateTime day) => _at(_weekdays, day.toLocal().weekday - 1, '');

  String shortWeekday(DateTime day) => _at(_shortWeekdays, day.toLocal().weekday - 1, '');

  /// "12 May", to look at (the day in the phone's time zone).
  String written(DateTime day) {
    final d = day.toLocal();
    return '${d.day} ${month(d.month)}';
  }

  /// "twelve May", to say: no digits.
  String spoken(DateTime day) {
    final d = day.toLocal();
    return '${number(d.day)} ${month(d.month)}';
  }

  /// "Today" or "Yesterday" when [day] is one of them, else null. [now] is the phone's clock.
  String? relative(DateTime day, DateTime now) => switch (daysAgo(day, now)) {
    0 => today,
    1 => yesterday,
    _ => null,
  };
}

final dateWordsProvider = Provider<DateWords>((ref) {
  final t = ref.watch(stringsProvider);
  return DateWords((key) => t(key));
});

/// [day] without the time of day, in the phone's time zone.
DateTime dayOnly(DateTime day) {
  final local = day.toLocal();
  return DateTime(local.year, local.month, local.day);
}

/// How many calendar days before [now] the day [day] is (0 today, 1 yesterday; negative in the future).
int daysAgo(DateTime day, DateTime now) {
  final a = dayOnly(day);
  final b = dayOnly(now);
  // Through UTC so a daylight saving change never makes a day 23 or 25 hours long.
  return DateTime.utc(b.year, b.month, b.day).difference(DateTime.utc(a.year, a.month, a.day)).inDays;
}
