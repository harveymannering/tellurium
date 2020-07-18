"""
Testing temiriam module
"""
from __future__ import absolute_import, print_function
from six import string_types
import roadrunner
from tellurium import temiriam

import unittest

class TeMiriamTests(unittest.TestCase):

    def test_getSBMLFromBiomodelsURN1(self):
        """ Check that string is returned.

        :return:
        """
        urn = 'urn:miriam:biomodels.db:BIOMD0000000139'
        sbml = temiriam.getSBMLFromBiomodelsURN(urn)
        assert sbml is not None
        # check that string
        self.assertIsInstance(sbml, string_types)

    def test_getSBMLFromBiomodelsURN2(self):
        """ Check that model can be loaded in roadrunner.

        :return:
        """
        urn = 'urn:miriam:biomodels.db:BIOMD0000000139'
        sbml = temiriam.getSBMLFromBiomodelsURN(urn)

        print("*" * 80)
        print(type(sbml))
        print("*" * 80)
        print(sbml)
        print("*" * 80)

        r = roadrunner.RoadRunner(sbml)
        self.assertFalse(r is None)
