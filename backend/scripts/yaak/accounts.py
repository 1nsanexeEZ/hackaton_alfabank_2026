"""Demo accounts of the seed and their tokens in the collection.

A token is a variable of the base environment: the latest response of the
role's login request, sent again once it is older than the token lives. So the
login is called once per role in 25 minutes and the stand's nginx limit of 10
logins a minute is never hit.
"""

from scripts.yaak.collection import answer, model_id, var

# JWT_ACCESS_TTL_MINUTES is 30: take a new token a bit earlier.
TOKEN_TTL_SECONDS = 25 * 60

# key → (login, who it is)
ACCOUNTS: dict[str, tuple[str, str]] = {
    "romashka": ("owner@romashka.test", "директор ООО «Ромашка»"),
    "accountant": ("accountant@romashka.test", "бухгалтер ООО «Ромашка»"),
    "ivanov": ("ivanov@ip.test", "ИП Иванов"),
    "vector": ("petrov@vector.test", "директор ООО «Вектор»"),
    "zakat": ("owner@zakat.test", "директор ООО «Закат»"),
    "progress": ("owner@progress.test", "директор ООО «Прогресс»"),
    "sboy": ("owner@sboy.test", "директор ООО «Сбой»"),
    "start": ("owner@start.test", "учредитель ООО «Старт»"),
    "underwriter": ("underwriter@bank.test", "андеррайтер банка"),
    "admin": (var("admin_login"), "администратор"),
}

INN = {
    "romashka": "7701158817",
    "ivanov": "770669871605",
    "vector": "7702987976",
    "zakat": "7703417070",
    "progress": "7704568152",
    "sboy": "7705729405",
    "start": "7706123455",
}


def login_request_id(who: str) -> str:
    return model_id("rq", f"login/{who}")


def token(who: str) -> str:
    return var(f"token_{who}")


def token_variables() -> dict[str, str]:
    return {
        f"token_{who}": answer(
            login_request_id(who), "$.access_token", behavior="ttl", ttl=TOKEN_TTL_SECONDS
        )
        for who in ACCOUNTS
    }


def login_body(who: str) -> dict[str, str]:
    login, _ = ACCOUNTS[who]
    password = var("admin_password") if who == "admin" else var("demo_password")
    return {"login": login, "password": password}
