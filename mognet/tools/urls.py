import yarl


def censor_credentials(url: str) -> str:
    return str(yarl.URL(url).with_password("**"))
