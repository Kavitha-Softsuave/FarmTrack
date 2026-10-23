import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/features/field/field_words.dart';
import 'package:farmtrack/core/theme/app_theme.dart';

import 'support/contrast.dart';

/// WCAG AA: 4.5:1 for text, 3:1 for graphics (icons, borders).
void main() {
  const aaText = 4.5;
  const aaGraphics = 3.0;

  test('the contrast helper agrees with the known extremes', () {
    expect(contrast(Colors.black, Colors.white), closeTo(21, 0.01));
    expect(contrast(Colors.white, Colors.white), closeTo(1, 0.001));
  });

  group('the three severity colours', () {
    for (final severity in Severity.values) {
      test('${severity.wire}: the text on the coloured band is AA (4.5:1)', () {
        final ratio = contrast(AppColors.onSeverity(severity), AppColors.severity(severity));
        expect(ratio, greaterThanOrEqualTo(aaText), reason: '${severity.wire} band: $ratio');
      });

      test('${severity.wire}: ink text on the soft panel is AA', () {
        final ratio = contrast(AppColors.ink, AppColors.severitySoft(severity));
        expect(ratio, greaterThanOrEqualTo(aaText), reason: '${severity.wire}: $ratio');
      });

      test('${severity.wire}: as an icon, border or text on light backgrounds (severityAccent) it is AA', () {
        final accent = AppColors.severityAccent(severity);
        expect(contrast(accent, AppColors.paper), greaterThanOrEqualTo(aaText), reason: 'on paper');
        expect(contrast(accent, AppColors.card), greaterThanOrEqualTo(aaText), reason: 'on white');
        expect(
          contrast(accent, AppColors.severitySoft(severity)),
          greaterThanOrEqualTo(aaGraphics),
          reason: 'on its panel',
        );
      });
    }

    test('the bright amber is a fill only: as an icon on a light panel it fails, which is why amberDark exists', () {
      // Recorded so nobody "simplifies" severityAccent back to amber: 1.8 to 2.0 is not readable.
      expect(contrast(AppColors.amber, AppColors.amberSoft), lessThan(aaGraphics));
      expect(contrast(AppColors.amber, AppColors.paper), lessThan(aaGraphics));
      expect(contrast(AppColors.amberDark, AppColors.amberSoft), greaterThanOrEqualTo(aaText));
      expect(AppColors.severityAccent(Severity.yellow), AppColors.amberDark);
    });
  });

  test('the text and background pairs added for the offline, ask, settings and demo screens are AA', () {
    final pairs = <String, double>{
      'white on blue (ask-own button)': contrast(Colors.white, AppColors.blue),
      'blue picture on white (suggestion cards)': contrast(AppColors.blue, AppColors.card),
      'ink on greenSoft (result ready card)': contrast(AppColors.ink, AppColors.greenSoft),
      'ink on amberSoft (waiting card)': contrast(AppColors.ink, AppColors.amberSoft),
      'inkSoft on paper (about line)': contrast(AppColors.inkSoft, AppColors.paper),
      'inkSoft on white (sources under an answer)': contrast(AppColors.inkSoft, AppColors.card),
      'ink on white (answer text)': contrast(AppColors.ink, AppColors.card),
      'amber on ink (demo date strip)': contrast(AppColors.amber, AppColors.ink),
      'white on green (count badge, tick)': contrast(Colors.white, AppColors.green),
      'amberDark on amberSoft (waiting card border)': contrast(AppColors.amberDark, AppColors.amberSoft),
    };
    pairs.forEach(
      (name, ratio) => expect(ratio, greaterThanOrEqualTo(aaText), reason: '$name: ${ratio.toStringAsFixed(2)}'),
    );
  });

  test('every foreground that used to be bright amber (amberDark, severityAccent) is AA on its background', () {
    final pairs = <String, double>{
      'amberDark on paper (diary empty picture, retake picture, expert picture)': contrast(
        AppColors.amberDark,
        AppColors.paper,
      ),
      'amberDark on white (cards, crop picture, error picture)': contrast(AppColors.amberDark, AppColors.card),
      'amberDark on amberSoft (warning tile, field "old" card, cereal crop picture)': contrast(
        AppColors.amberDark,
        AppColors.amberSoft,
      ),
      'ink on amber (diary plus, "I sprayed" fill buttons)': contrast(AppColors.ink, AppColors.amber),
    };
    pairs.forEach(
      (name, ratio) => expect(ratio, greaterThanOrEqualTo(aaText), reason: '$name: ${ratio.toStringAsFixed(2)}'),
    );
  });

  test('the forecast and reading-tile pictures are readable (3:1 graphics) on the white cards they sit on', () {
    for (final mm in [0.0, 5.0, 20.0]) {
      expect(
        contrast(forecastColor(mm), AppColors.card),
        greaterThanOrEqualTo(aaGraphics),
        reason: 'forecast colour for $mm mm',
      );
    }
    final tiles = readingTiles(
      const ReadingsOut(tempC: 20, rhPct: 60, rain24hMm: 2, leafWetnessMin: 100, soilMoisturePct: 30),
    );
    expect(tiles, hasLength(5));
    for (final tile in tiles) {
      expect(
        contrast(tile.color, AppColors.card),
        greaterThanOrEqualTo(aaGraphics),
        reason: 'tile ${tile.id}: ${contrast(tile.color, AppColors.card)}',
      );
    }
  });
}
