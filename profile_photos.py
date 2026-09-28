import os
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename


ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PROFILE_PHOTO_PIXELS = 25_000_000
SUPPORTED_IMAGE_FORMATS = {'png', 'jpeg', 'gif', 'webp'}


class ProfilePhotoError(ValueError):
    pass


def save_profile_photo(upload, user_id, storage_path):
    if not storage_path:
        raise ProfilePhotoError(
            'Persistent photo storage is not configured. Contact the site administrator.'
        )

    safe_name = secure_filename(upload.filename or '')
    if '.' not in safe_name:
        raise ProfilePhotoError('Choose a PNG, JPG, GIF, or WEBP image.')

    extension = safe_name.rsplit('.', 1)[1].lower()
    if extension not in ALLOWED_PHOTO_EXTENSIONS:
        raise ProfilePhotoError('Choose a PNG, JPG, GIF, or WEBP image.')

    upload.stream.seek(0, os.SEEK_END)
    file_size = upload.stream.tell()
    upload.stream.seek(0)
    if file_size > MAX_PROFILE_PHOTO_BYTES:
        raise ProfilePhotoError('Profile photos must be 5 MB or smaller.')

    temporary_path = None
    try:
        with Image.open(upload.stream) as image:
            if image.width * image.height > MAX_PROFILE_PHOTO_PIXELS:
                raise ProfilePhotoError('Profile photos must be 25 megapixels or smaller.')
            image_format = (image.format or '').lower()
            image.verify()
        if image_format not in SUPPORTED_IMAGE_FORMATS:
            raise ProfilePhotoError('The uploaded file is not a supported image.')

        upload.stream.seek(0)
        with Image.open(upload.stream) as image:
            if image.width * image.height > MAX_PROFILE_PHOTO_PIXELS:
                raise ProfilePhotoError('Profile photos must be 25 megapixels or smaller.')
            image = ImageOps.exif_transpose(image)
            image.seek(0)
            image.load()
            output = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')

        os.makedirs(storage_path, exist_ok=True)
        filename = f'user_{user_id}_{uuid.uuid4().hex}.webp'
        file_path = os.path.join(storage_path, filename)
        temporary_path = f'{file_path}.tmp'
        output.save(temporary_path, format='WEBP', quality=85, method=6)
        os.replace(temporary_path, file_path)
    except ProfilePhotoError:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise ProfilePhotoError('The uploaded file could not be read as a valid image.') from error

    return f'profile_photos/{filename}', file_path


def remove_profile_photo(photo_reference, storage_path, legacy_path=None):
    if not photo_reference or '://' in str(photo_reference):
        return

    reference = str(photo_reference).replace('\\', '/')
    parts = reference.split('/')
    if len(parts) == 2 and parts[0] == 'profile_photos':
        directories = [storage_path]
    elif len(parts) == 3 and parts[:2] == ['uploads', 'profile_photos']:
        directories = [legacy_path]
    else:
        return

    filename = parts[-1]
    for directory in directories:
        if not directory:
            continue
        file_path = os.path.abspath(os.path.join(directory, filename))
        if os.path.dirname(file_path) != os.path.abspath(directory):
            continue
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass
        except OSError:
            pass