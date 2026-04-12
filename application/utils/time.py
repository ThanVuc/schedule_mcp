def timestamp_suffix() -> str:
    from datetime import datetime

    return datetime.now().strftime("-%Y%m%d-%H%M%S")