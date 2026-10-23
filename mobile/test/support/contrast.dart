import 'dart:math' as math;

import 'package:flutter/painting.dart';

/// WCAG relative luminance of [color] (0 = black, 1 = white).
double luminance(Color color) {
  double channel(double v) => v <= 0.03928 ? v / 12.92 : math.pow((v + 0.055) / 1.055, 2.4).toDouble();
  return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
}

/// WCAG contrast ratio of two colours, from 1 (identical) to 21 (black on white). AA needs 4.5 for text and 3 for
/// large text and graphics.
double contrast(Color a, Color b) {
  final la = luminance(a);
  final lb = luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}
