import os
from os import path

import pytest
from django.utils.functional import cached_property

from sentry import eventstore
from sentry.event_manager import EventManager, get_event_type, materialize_metadata
from sentry.eventstore.models import Event
from sentry.grouping.api import (
    GroupingConfig,
    apply_server_fingerprinting,
    get_default_grouping_config_dict,
    load_grouping_config,
)
from sentry.grouping.enhancer import Enhancements
from sentry.grouping.fingerprinting import FingerprintingRules
from sentry.stacktraces.processing import normalize_stacktraces_for_grouping
from sentry.utils import json

GROUPING_INPUTS_DIR = path.join(path.dirname(__file__), "grouping_inputs")
FINGERPRINT_INPUTS_DIR = path.join(path.dirname(__file__), "fingerprint_inputs")


class GroupingInput:
    def __init__(self, inputs_dir: str, filename: str):
        self.filename = filename  # Necessary for test naming
        with open(path.join(inputs_dir, self.filename)) as f:
            self.data = json.load(f)

    def _manually_save_event(self, grouping_config: GroupingConfig) -> Event:
        """
        Manually complete the steps to save an event, in such a way as to not touch postgres (which
        makes it run a lot faster).
        """
        mgr = EventManager(data=self.data, grouping_config=grouping_config)
        mgr.normalize()
        data = mgr.get_data()

        # Normalize the stacktrace for grouping.  This normally happens in `EventManager.save`.
        normalize_stacktraces_for_grouping(data, load_grouping_config(grouping_config))

        return eventstore.backend.create_event(data=data)

    def create_event(self, config_name: str) -> Event:
        grouping_config = get_default_grouping_config_dict(config_name)

        # Add in any extra grouping configuration from the input data
        grouping_config["enhancements"] = Enhancements.from_config_string(
            self.data.get("_grouping", {}).get("enhancements", ""),
            bases=Enhancements.loads(grouping_config["enhancements"]).bases,
        ).dumps()

        event = self._manually_save_event(grouping_config)

        return event


def get_grouping_inputs(inputs_dir: str) -> list[GroupingInput]:
    return [
        GroupingInput(inputs_dir, filename)
        for filename in sorted(os.listdir(inputs_dir))
        if filename.endswith(".json")
    ]


def with_grouping_inputs(test_param_name: str, inputs_dir: str) -> pytest.MarkDecorator:
    grouping_inputs = get_grouping_inputs(inputs_dir)
    return pytest.mark.parametrize(
        test_param_name,
        grouping_inputs,
        ids=lambda grouping_input: grouping_input.filename.replace("-", "_").replace(".json", ""),
    )


class FingerprintInput:
    def __init__(self, filename):
        self.filename = filename

    @cached_property
    def data(self):
        with open(path.join(FINGERPRINT_INPUTS_DIR, self.filename)) as f:
            return json.load(f)

    def create_event(self):
        config = FingerprintingRules.from_json(
            {"rules": self.data.get("_fingerprinting_rules", [])},
        )
        mgr = EventManager(data=self.data)
        mgr.normalize()
        data = mgr.get_data()

        data.setdefault("fingerprint", ["{{ default }}"])
        apply_server_fingerprinting(data, config)
        event_type = get_event_type(data)
        event_metadata = event_type.get_metadata(data)
        data.update(materialize_metadata(data, event_type, event_metadata))

        evt = eventstore.backend.create_event(data=data)
        return config, evt


fingerprint_input = list(
    FingerprintInput(filename)
    for filename in os.listdir(FINGERPRINT_INPUTS_DIR)
    if filename.endswith(".json")
)


def with_fingerprint_input(name):
    return pytest.mark.parametrize(
        name, fingerprint_input, ids=lambda x: x.filename[:-5].replace("-", "_")
    )
