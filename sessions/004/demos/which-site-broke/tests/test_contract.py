from server.main import node_record


def test_node_seven_is_the_only_old_version():
    nodes = [node_record(i) for i in range(1, 11)]
    assert [node["node_id"] for node in nodes if node["app_version"] == "1.8.3"] == ["edge-07"]
    assert nodes[0]["asset_id"] == "turbine-01"
    assert nodes[-1]["asset_id"] == "turbine-10"
