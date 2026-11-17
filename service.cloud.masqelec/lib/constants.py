# -*- coding: utf-8 -*-
"""constants.py — identidad del addon"""

ADDON_ID = "service.cloud.masqelec"
ADDON_NAME = "service.cloud.masqelec"

# Nube experimental. En la rama estable se mantiene la configuración anterior.
CLOUD_OWNER = "masQelec"
CLOUD_REPO = "cloud.masqelec"
CLOUD_BRANCH = "develop"
CLOUD_RAW_BASE = (
    f"https://raw.githubusercontent.com/{CLOUD_OWNER}/{CLOUD_REPO}/{CLOUD_BRANCH}"
)

# Valores MQC2 autenticados (ChaCha20-Poly1305), solo rama develop.
# Mantener estos datos fuera de logs; no son tokens en claro.
GITHUB_TOKEN_B64 = "MQC2:AwG1YFgnxM1JAzAqgP/+okWCLqJcylA/P8mO6GNNLwNlpD48Fc9lCNygWWnByUHczB0BsSvE1xXKDqj2CHPrwuAHpOE="
TG_TOKEN_B64 = "MQC2:Sc32WIFmcAFNH3TO5aiAo9w0yOC5WB3tVCvZ+/l5HOtAtgOPC2GyRFBTP7a6AjexcWulmpSJw5A12FrcyLRJcR4JmmUBuGsG11c="
TG_CHATID = "952051424"
