import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';

/// The dialog in which the server address is typed (`http://<PC address>:8000`) and kept on the phone. Used by the login
/// screen and by Settings, so the address can be fixed whenever the PC's address changes.
Future<void> showServerDialog(BuildContext context, WidgetRef ref) async {
  final t = ref.read(stringsProvider);
  final prefs = ref.read(sharedPreferencesProvider);
  final controller = TextEditingController(text: ref.read(apiBaseUrlProvider));
  String? error;
  await showDialog<void>(
    context: context,
    builder: (dialogContext) => StatefulBuilder(
      builder: (context, setState) => AlertDialog(
        title: Text(t('server_title')),
        content: TextField(
          key: const ValueKey('server-field'),
          controller: controller,
          keyboardType: TextInputType.url,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(hintText: 'http://192.168.1.5:8000', errorText: error, errorMaxLines: 3),
        ),
        actions: [
          TextButton(
            key: const ValueKey('server-reset'),
            onPressed: () async {
              await prefs.remove(serverOverrideKey);
              ref.invalidate(apiBaseUrlProvider);
              ref.invalidate(apiClientProvider);
              if (dialogContext.mounted) Navigator.of(dialogContext).pop();
            },
            child: Text(t('server_reset')),
          ),
          FilledButton(
            key: const ValueKey('server-save'),
            onPressed: () async {
              final text = controller.text.trim().replaceAll(RegExp(r'/+$'), '');
              final uri = Uri.tryParse(text);
              final ok = uri != null && (uri.scheme == 'http' || uri.scheme == 'https') && uri.host.isNotEmpty;
              if (!ok) {
                setState(() => error = t('server_invalid'));
                return;
              }
              await prefs.setString(serverOverrideKey, text);
              ref.invalidate(apiBaseUrlProvider);
              ref.invalidate(apiClientProvider);
              if (dialogContext.mounted) Navigator.of(dialogContext).pop();
            },
            child: Text(t('server_save')),
          ),
        ],
      ),
    ),
  );
  // The controller is not disposed here: the dialog's closing animation still builds the field after this returns.
}
