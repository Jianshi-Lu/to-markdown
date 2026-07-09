class AppError(Exception):
    code = "app_error"
    status_code = 500


class ConversionError(AppError):
    code = "conversion_failed"
    status_code = 422


class OmlxUnavailableError(AppError):
    code = "omlx_unavailable"
    status_code = 503


class UploadTooLargeError(AppError):
    code = "upload_too_large"
    status_code = 413

