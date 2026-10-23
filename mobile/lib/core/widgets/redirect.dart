import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Sends the farmer to [to] once the first frame is done. Used when a screen opens without the state it needs
/// (for example a scan result after the app was restarted).
class Redirect extends StatefulWidget {
  const Redirect({super.key, required this.to});

  final String to;

  @override
  State<Redirect> createState() => _RedirectState();
}

class _RedirectState extends State<Redirect> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.go(widget.to);
    });
  }

  @override
  Widget build(BuildContext context) => const Scaffold(body: SizedBox.shrink());
}
