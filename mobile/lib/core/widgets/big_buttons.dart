import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../utils/haptics.dart';

/// A round picture button. Primary actions use [Dimens.primary] (96 dp) or more; nothing is below 64 dp.
class BigIconButton extends StatelessWidget {
  const BigIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    required this.semanticLabel,
    this.color = AppColors.green,
    this.foreground = Colors.white,
    this.size = Dimens.primary,
    this.label,
  }) : assert(size >= Dimens.minTouch, 'touch targets must be at least 64 dp');

  final IconData icon;
  final VoidCallback? onPressed;
  final String semanticLabel;
  final Color color;
  final Color foreground;
  final double size;

  /// Optional word under the picture (kept very short).
  final String? label;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    final button = Material(
      color: enabled ? color : AppColors.line,
      shape: const CircleBorder(),
      elevation: enabled ? 3 : 0,
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: enabled
            ? () {
                Haptics.tap();
                onPressed!();
              }
            : null,
        child: SizedBox(
          width: size,
          height: size,
          child: Icon(icon, size: size * 0.58, color: enabled ? foreground : AppColors.inkSoft),
        ),
      ),
    );
    return Semantics(
      button: true,
      enabled: enabled,
      label: semanticLabel,
      excludeSemantics: true,
      child: label == null
          ? button
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                button,
                const SizedBox(height: 6),
                // Never wider than the button (plus a little), whatever the text size: it shrinks to fit.
                SizedBox(
                  width: size + 24,
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(label!, textAlign: TextAlign.center, style: Theme.of(context).textTheme.labelLarge),
                  ),
                ),
              ],
            ),
    );
  }
}

/// The green tick: "yes" / "continue" / "send".
class TickButton extends StatelessWidget {
  const TickButton({super.key, required this.onPressed, required this.semanticLabel, this.size = Dimens.primary});

  final VoidCallback? onPressed;
  final String semanticLabel;
  final double size;

  @override
  Widget build(BuildContext context) => BigIconButton(
    icon: AppIcons.tick,
    onPressed: onPressed,
    semanticLabel: semanticLabel,
    color: AppColors.green,
    size: size,
  );
}

/// The red cross: "no" / "remove".
class CrossButton extends StatelessWidget {
  const CrossButton({super.key, required this.onPressed, required this.semanticLabel, this.size = Dimens.primary});

  final VoidCallback? onPressed;
  final String semanticLabel;
  final double size;

  @override
  Widget build(BuildContext context) => BigIconButton(
    icon: AppIcons.cross,
    onPressed: onPressed,
    semanticLabel: semanticLabel,
    color: AppColors.red,
    size: size,
  );
}

/// A large rounded picture tile (Home buttons, crop choices). [child] is the picture; [label] a short word.
class PictureTile extends StatelessWidget {
  const PictureTile({
    super.key,
    required this.child,
    required this.onPressed,
    required this.semanticLabel,
    this.label,
    this.color = AppColors.card,
    this.borderColor = AppColors.green,
    this.minHeight = Dimens.primary,
  });

  final Widget child;
  final VoidCallback? onPressed;
  final String semanticLabel;
  final String? label;
  final Color color;
  final Color borderColor;
  final double minHeight;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      excludeSemantics: true,
      child: Material(
        color: color,
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Dimens.radius),
          side: BorderSide(color: borderColor, width: 3),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(Dimens.radius),
          onTap: onPressed == null
              ? null
              : () {
                  Haptics.tap();
                  onPressed!();
                },
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: minHeight, minWidth: Dimens.minTouch),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Flexible(
                    child: FittedBox(fit: BoxFit.scaleDown, child: child),
                  ),
                  if (label != null) ...[
                    const SizedBox(height: 8),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(label!, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleLarge),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
