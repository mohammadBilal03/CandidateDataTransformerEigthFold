from eightfold.normalize import (
    normalize_phone, normalize_date, normalize_skill, normalize_country, normalize_email,
)


def test_phone_e164_us():
    val, conf, err = normalize_phone("(415) 555-0142", default_region="US")
    assert val == "+14155550142"
    assert conf > 0.8


def test_phone_garbage_returns_null_not_crash():
    val, conf, err = normalize_phone("not-a-phone-#@!")
    assert val is None
    assert conf < 0.5
    assert err is not None


def test_phone_empty():
    val, conf, err = normalize_phone("")
    assert val is None


def test_date_iso():
    val, conf, err = normalize_date("2021-03-15")
    assert val == "2021-03"


def test_date_month_name():
    val, conf, err = normalize_date("March 2021")
    assert val == "2021-03"


def test_date_present_sentinel():
    val, conf, err = normalize_date("present")
    assert val == "present"


def test_date_garbage():
    val, conf, err = normalize_date("not a date")
    assert val is None
    assert err is not None


def test_skill_synonym_canonicalization():
    val, conf, err = normalize_skill("JS")
    assert val == "javascript"
    val2, _, _ = normalize_skill("javascript")
    assert val2 == val


def test_skill_unknown_passthrough_lowercased():
    val, conf, err = normalize_skill("Rust")
    assert val == "rust"


def test_country_alias():
    val, conf, err = normalize_country("United States")
    assert val == "US"


def test_country_already_iso():
    val, conf, err = normalize_country("gb")
    assert val == "GB"


def test_country_unknown():
    val, conf, err = normalize_country("Narnia")
    assert val is None


def test_email_valid():
    val, conf, err = normalize_email("Jane.Doe@Example.com")
    assert val == "jane.doe@example.com"


def test_email_malformed():
    val, conf, err = normalize_email("not-an-email")
    assert val is None
