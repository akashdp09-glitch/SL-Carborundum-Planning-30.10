from suite.hub_auth import issue, validate


def test_tab_ticket_validates_and_expires(tmp_path):
    token=issue(tmp_path,"planner","planning",now=1000)
    assert validate(tmp_path,token,now=1001)=={"username":"planner","role":"planning"}
    assert validate(tmp_path,token,now=1000+8*60*60) is None
    assert validate(tmp_path,token+"x",now=1001) is None
