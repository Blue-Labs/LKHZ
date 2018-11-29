'''
pytest
'''

import lkhz
import pytest

class App:
    def __init__(self):
        self.lkhz = lkhz.LKHZ()

@pytest.fixture(scope='module')
def app():
    return App()

def test_lkhz(app):
    assert app.lkhz.analyze()
