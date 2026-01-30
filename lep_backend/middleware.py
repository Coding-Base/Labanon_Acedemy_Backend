"""Backward-compat shim: re-export CloudFrontOriginMiddleware from the
middleware package module so imports from `lep_backend.middleware` still work."""

from lep_backend.middleware.cloudfront import CloudFrontOriginMiddleware  # pragma: no cover
