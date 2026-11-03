from suite.daily_status_files import section_from_filename


def test_numeric_daily_status_section_prefixes():
    names = {
        "1 Preparation Daily Status.xlsx": "Preparation",
        "2-Mixing-October.xlsx": "Mixing",
        "3_Forming.xlsx": "Forming",
        "4.Firing.xlsx": "Firing",
        "5 Grinding-Cutting.xlsx": "Grinding",
        "6Packing.xlsx": "Packing",
    }
    for name, section in names.items():
        assert section_from_filename(name) == section


def test_unknown_or_nonleading_number_does_not_guess():
    assert section_from_filename("7 Other.xlsx") == ""
    assert section_from_filename("Daily Status 1 Preparation.xlsx") == ""
    assert section_from_filename("12 Preparation.xlsx") == ""
