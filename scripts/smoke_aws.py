"""Compatibility entry point for existing AWS deployment automation."""
if __package__:
    from .smoke_cloud import check_endpoint, main
else:
    from smoke_cloud import check_endpoint, main

if __name__ == "__main__":
    raise SystemExit(main())
