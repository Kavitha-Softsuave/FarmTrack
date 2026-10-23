import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/api_exception.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/voice/voice_service.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'server_dialog.dart';

/// The one login screen (route `/login`): a user name and a password typed with the phone's own keyboard, then the big
/// green tick. The app always asks for it; the session itself stays in the secure token store. Only the last user name
/// is remembered (in SharedPreferences) and prefilled, never the password.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  /// Same rules as the server: 3 to 40 characters of a to z, 0 to 9, dot, underscore and minus; password 6 or more.
  static final _usernameShape = RegExp(r'^[a-z0-9._-]{3,40}$');
  static const _minPassword = 6;

  final Object _owner = Object();
  late final TextEditingController _username;
  final TextEditingController _password = TextEditingController();
  final FocusNode _usernameFocus = FocusNode();
  final FocusNode _passwordFocus = FocusNode();
  bool _hidden = true;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _username = TextEditingController(text: ref.read(settingsStoreProvider).loadLastUsername() ?? '');
  }

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    _usernameFocus.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  Future<void> _say(List<String> ids) => ref.read(voiceServiceProvider).speakPrompts(ids, owner: _owner);

  void _toggleHidden() {
    setState(() => _hidden = !_hidden);
    _say([_hidden ? 'login_hide_password' : 'login_show_password']);
  }

  Future<void> _fail(String promptId) async {
    Haptics.error();
    await _say([promptId]);
  }

  Future<void> _submit() async {
    if (_busy) return;
    final username = _username.text.trim().toLowerCase();
    final password = _password.text;
    if (username.isEmpty || password.isEmpty) {
      (username.isEmpty ? _usernameFocus : _passwordFocus).requestFocus();
      await _fail('login_fields_needed');
      return;
    }
    // Such a pair can never exist: say "not right" without asking the server.
    if (!_usernameShape.hasMatch(username) || password.length < _minPassword) {
      await _fail('login_wrong');
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() => _busy = true);
    try {
      final token = await ref
          .read(apiClientProvider)
          .login(username: username, password: password, deviceId: ref.read(deviceIdProvider));
      if (!mounted) return;
      await ref.read(settingsStoreProvider).saveLastUsername(username);
      await ref.read(sessionProvider.notifier).login(token);
      await ref.read(sessionProvider.notifier).syncLanguage(ref.read(languageProvider));
      Haptics.success();
      if (mounted) context.go(Routes.homeFresh);
    } on ApiException catch (e) {
      if (!mounted) return;
      final wrong = e.code == 'invalid_credentials' || e.kind == ApiErrorKind.validation;
      await _fail(wrong ? 'login_wrong' : errorPromptFor(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    return VoiceScaffold(
      owner: _owner,
      script: promptList(const ['login_intro', 'login_ask_username', 'login_ask_password', 'login_tap_tick']),
      onBack: () => context.go(Routes.welcome),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _FieldLabel(icon: AppIcons.person, text: t('login_username_label')),
          const SizedBox(height: 8),
          Semantics(
            label: t('login_username_label'),
            child: TextField(
              key: const ValueKey('login-username'),
              controller: _username,
              focusNode: _usernameFocus,
              autofocus: _username.text.isEmpty,
              enabled: !_busy,
              keyboardType: TextInputType.text,
              textInputAction: TextInputAction.next,
              textCapitalization: TextCapitalization.none,
              autocorrect: false,
              enableSuggestions: false,
              maxLength: 40,
              style: Theme.of(context).textTheme.titleMedium,
              decoration: _decoration(),
              onSubmitted: (_) => _passwordFocus.requestFocus(),
            ),
          ),
          const SizedBox(height: 16),
          _FieldLabel(icon: AppIcons.lock, text: t('login_password_label')),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Semantics(
                  label: t('login_password_label'),
                  child: TextField(
                    key: const ValueKey('login-password'),
                    controller: _password,
                    focusNode: _passwordFocus,
                    autofocus: _username.text.isNotEmpty,
                    enabled: !_busy,
                    obscureText: _hidden,
                    // Plain letters and numbers, no suggestions or learned words.
                    keyboardType: TextInputType.visiblePassword,
                    textInputAction: TextInputAction.done,
                    autocorrect: false,
                    enableSuggestions: false,
                    maxLength: 128,
                    style: Theme.of(context).textTheme.titleMedium,
                    decoration: _decoration(),
                    onSubmitted: (_) => _submit(),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              BigIconButton(
                key: const ValueKey('login-eye'),
                icon: _hidden ? AppIcons.eye : AppIcons.eyeOff,
                semanticLabel: t(_hidden ? 'login_show_password' : 'login_hide_password'),
                color: AppColors.card,
                foreground: AppColors.ink,
                size: 72,
                onPressed: _toggleHidden,
              ),
            ],
          ),
          if (_busy) const Padding(padding: EdgeInsets.only(top: 16), child: LinearProgressIndicator()),
          // Only against a real server: which PC or server the test phone talks to (never shown with the demo mock).
          if (!ref.watch(appConfigProvider).useMockApi) _ServerLink(enabled: !_busy),
        ],
      ),
      bottomRight: TickButton(
        key: const ValueKey('login-submit'),
        semanticLabel: t('a11y_login'),
        onPressed: _busy ? null : _submit,
      ),
    );
  }

  InputDecoration _decoration() => InputDecoration(
    counterText: '',
    filled: true,
    fillColor: AppColors.card,
    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(20),
      borderSide: const BorderSide(color: AppColors.ink, width: 2),
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(20),
      borderSide: const BorderSide(color: AppColors.blue, width: 3),
    ),
    disabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(20),
      borderSide: const BorderSide(color: AppColors.line, width: 2),
    ),
  );
}

/// A picture and a word above a field.
class _FieldLabel extends StatelessWidget {
  const _FieldLabel({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: Row(
      children: [
        Icon(icon, size: 32, color: AppColors.green),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: Theme.of(context).textTheme.titleLarge)),
      ],
    ),
  );
}

/// A small link under the login fields: opens a dialog to type the server address (`http://<PC address>:8000`).
class _ServerLink extends ConsumerWidget {
  const _ServerLink({required this.enabled});

  final bool enabled;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final url = ref.watch(apiBaseUrlProvider);
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: TextButton.icon(
        key: const ValueKey('server-link'),
        style: TextButton.styleFrom(minimumSize: const Size(64, 56), foregroundColor: AppColors.inkSoft),
        onPressed: enabled ? () => showServerDialog(context, ref) : null,
        icon: const Icon(Icons.dns_rounded),
        label: Text('${t('login_server')}: $url', overflow: TextOverflow.ellipsis, maxLines: 1),
      ),
    );
  }
}
