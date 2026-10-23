import 'package:flutter/material.dart';

import 'diary_entry_screen.dart';
import 'diary_list_screen.dart';

/// Route `/diary`. Opened from an advice card ("I sprayed") with the advice preselected, [adviceId], [cropId] and
/// [productId] come from the query keys `advice`, `crop` and `product` (see `Routes.diaryFor`): the farmer only
/// confirms with the green tick. Opened from Home it is the diary list (newest first, with a plus button to write
/// a spray that was not advised).
class DiaryScreen extends StatelessWidget {
  const DiaryScreen({super.key, this.adviceId, this.cropId, this.productId});

  final String? adviceId;
  final String? cropId;
  final String? productId;

  @override
  Widget build(BuildContext context) {
    final advice = adviceId;
    if (advice == null || advice.isEmpty) return const DiaryListScreen();
    return DiaryEntryScreen(adviceId: advice, cropId: cropId, productId: productId);
  }
}

/// Route `/diary/add`: "Write a spray I did" (crop, medicine name, day).
class DiaryAddScreen extends StatelessWidget {
  const DiaryAddScreen({super.key});

  @override
  Widget build(BuildContext context) => const DiaryEntryScreen();
}
