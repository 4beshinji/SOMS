"""Model factory with automatic fallback from Mamba to Transformer."""
from loguru import logger


def create_model(arch: str = "auto", **kwargs):
    """Create a forecaster model.

    Args:
        arch: "auto" (try mamba, fallback to transformer), "mamba", or "transformer"
        **kwargs: passed to model constructor

    Returns:
        nn.Module instance
    """
    if arch in ("auto", "mamba"):
        try:
            from model.mamba_forecaster import MambaForecaster

            model = MambaForecaster(**kwargs)
            logger.info("Created MambaForecaster ({})", arch)
            return model
        except (ImportError, Exception) as e:
            if arch == "mamba":
                raise
            logger.warning("mamba-ssm unavailable ({}), using Transformer fallback", e)

    from model.transformer_forecaster import TransformerForecaster

    model = TransformerForecaster(**kwargs)
    logger.info("Created TransformerForecaster")
    return model
