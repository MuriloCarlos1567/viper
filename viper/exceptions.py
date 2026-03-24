class ViperError(Exception):
    """Excecao base do Viper."""


class ValidationError(ViperError):
    """Falha de validacao de repositorio/configuracao."""


class EnvParseError(ViperError):
    """Falha ao interpretar arquivo .env."""


class PortConflictError(ViperError):
    """Conflito quando dois servicos querem a mesma porta no host."""
