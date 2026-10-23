import 'dart:io' show Platform;

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

/// The farmer refused (or the phone forbids) camera access.
class CameraPermissionDenied implements Exception {
  const CameraPermissionDenied();
}

/// Takes photos with the system camera or picks them from the gallery. Tests use a fake.
abstract interface class PhotoPicker {
  /// Opens the camera and returns the photo path, or null if the farmer came back without a photo.
  /// Throws [CameraPermissionDenied].
  Future<String?> takePhoto();

  /// Opens the phone's gallery (the system photo picker) and returns the chosen photo paths, at most [limit] of them
  /// (empty if the farmer came back without choosing). No permission is needed: the system picker hands over only the
  /// photos the farmer taps.
  Future<List<String>> pickFromGallery({int limit = 1});

  /// On Android the camera app can make the system close ours; the photo taken is then handed back on the next
  /// start. Returns its path, or null.
  Future<String?> recoverLostPhoto();
}

/// `image_picker`: the phone's own camera app (nothing for us to keep alive, so it is light on 3 GB phones).
/// JPEG quality 80 and at most 1600 px on the long side keeps an upload to a few hundred KB on weak networks.
class ImagePickerService implements PhotoPicker {
  ImagePickerService([ImagePicker? picker]) : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  static const imageQuality = 80;
  static const maxSide = 1600.0;

  @override
  Future<String?> takePhoto() async {
    try {
      final file = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: imageQuality,
        maxWidth: maxSide,
        maxHeight: maxSide,
        preferredCameraDevice: CameraDevice.rear,
      );
      return file?.path;
    } on PlatformException catch (e) {
      if (e.code == 'camera_access_denied' || e.code == 'camera_access_restricted') {
        throw const CameraPermissionDenied();
      }
      rethrow;
    }
  }

  @override
  Future<List<String>> pickFromGallery({int limit = 1}) async {
    if (limit <= 0) return const [];
    if (limit == 1) {
      final file = await _picker.pickImage(
        source: ImageSource.gallery,
        imageQuality: imageQuality,
        maxWidth: maxSide,
        maxHeight: maxSide,
      );
      return file == null ? const [] : [file.path];
    }
    // image_picker needs a limit of at least 2 for several photos.
    final files = await _picker.pickMultiImage(
      imageQuality: imageQuality,
      maxWidth: maxSide,
      maxHeight: maxSide,
      limit: limit,
    );
    return [for (final f in files.take(limit)) f.path];
  }

  @override
  Future<String?> recoverLostPhoto() async {
    if (!Platform.isAndroid) return null;
    try {
      final lost = await _picker.retrieveLostData();
      if (lost.isEmpty) return null;
      return lost.file?.path;
    } catch (_) {
      return null;
    }
  }
}

final photoPickerProvider = Provider<PhotoPicker>((ref) => ImagePickerService());
