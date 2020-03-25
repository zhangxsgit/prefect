from unittest.mock import MagicMock

import pytest

from prefect.agent.nomad import NomadAgent
from prefect.environments.storage import Docker, Local
from prefect.utilities.configuration import set_temporary_config
from prefect.utilities.graphql import GraphQLResult


def test_nomad_agent_init(runner_token):
    agent = NomadAgent()
    assert agent
    assert agent.labels == []
    assert agent.name == "agent"


def test_nomad_agent_config_options(runner_token):
    with set_temporary_config({"agent.auth_token": "TEST_TOKEN"}):
        agent = NomadAgent(name="test")
        assert agent
        assert agent.name == "test"
        assert agent.client.get_auth_token() == "TEST_TOKEN"
        assert agent.logger


def test_nomad_agent_deploy_flow(monkeypatch, runner_token):
    post = MagicMock()
    import requests  # this is imported within the agent's constructor

    monkeypatch.setattr(requests, "post", post)

    with set_temporary_config({"api": "https://api.prefect.io"}):
        agent = NomadAgent()
        agent.deploy_flow(
            flow_run=GraphQLResult(
                {
                    "flow": GraphQLResult(
                        {
                            "storage": Docker(
                                registry_url="test", image_name="name", image_tag="tag"
                            ).serialize(),
                            "id": "id",
                        }
                    ),
                    "id": "id",
                }
            )
        )

        assert post.called
        assert post.call_args[1]["json"]


def test_nomad_agent_deploy_flow_raises(monkeypatch, runner_token):
    post = MagicMock()
    import requests  # this is imported within the agent's constructor

    monkeypatch.setattr(requests, "post", post)

    agent = NomadAgent()

    with pytest.raises(ValueError):
        agent.deploy_flow(
            flow_run=GraphQLResult(
                {
                    "flow": GraphQLResult({"storage": Local().serialize(), "id": "id"}),
                    "id": "id",
                }
            )
        )

    assert not post.called


@pytest.mark.parametrize("flag", [True, False])
def test_nomad_agent_replace_yaml(runner_token, flag):
    with set_temporary_config({"agent.auth_token": "token"}):
        flow_run = GraphQLResult(
            {
                "flow": GraphQLResult(
                    {
                        "storage": Docker(
                            registry_url="test", image_name="name", image_tag="tag"
                        ).serialize(),
                        "id": "id",
                    }
                ),
                "id": "id",
            }
        )

        with set_temporary_config({"logging.log_to_api": flag}):
            agent = NomadAgent(env_vars=dict(AUTH_THING="foo", PKG_SETTING="bar"))
        job = agent.replace_job_spec_json(flow_run)

        assert job["Job"]["TaskGroups"][0]["Tasks"][0]["Name"] == "id"
        assert (
            job["Job"]["TaskGroups"][0]["Tasks"][0]["Config"]["image"]
            == "test/name:tag"
        )

        env = job["Job"]["TaskGroups"][0]["Tasks"][0]["Env"]
        assert env["PREFECT__API"] == "http://localhost:4200"
        assert env["PREFECT__AGENT__AUTH_TOKEN"] == "token"
        assert env["PREFECT__CONTEXT__FLOW_RUN_ID"] == "id"
        assert env["PREFECT__CONTEXT__NAMESPACE"] == "default"
        assert env["PREFECT__LOGGING__LOG_TO_API"] == str(flag).lower()
        assert env["AUTH_THING"] == "foo"
        assert env["PKG_SETTING"] == "bar"
