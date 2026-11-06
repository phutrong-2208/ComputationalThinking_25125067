import json
import os
from importlib.resources import files

import pytest

from exam_baseline.models import GeneratedExam, GenerationRequest
from exam_baseline.samples import sample_request


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch):
    for key in list(os.environ):
        if key.startswith("EXAM_"):
            monkeypatch.delenv(key)


@pytest.fixture
def payload():
    return sample_request().model_dump(mode="json")


@pytest.fixture
def request_model(payload):
    return GenerationRequest.model_validate(payload)


@pytest.fixture
def exam_dict():
    return json.loads(files("exam_baseline.fixtures").joinpath("mock_exam.json").read_text("utf-8"))


@pytest.fixture
def exam(exam_dict):
    return GeneratedExam.model_validate(exam_dict)
