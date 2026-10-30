import os
import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get('TETHER_RUN_INTEGRATION') == '1':
        return
    skip = pytest.mark.skip(reason='Set TETHER_RUN_INTEGRATION=1 for safe local-machine checks')
    for item in items:
        if 'integration' in item.keywords:
            item.add_marker(skip)
