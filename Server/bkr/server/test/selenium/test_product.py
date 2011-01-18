#!/usr/bin/python

import bkr.server.test.selenium
from bkr.server.test import data_setup
import unittest, time, re, os
from turbogears.database import session

class TestProduct(bkr.server.test.selenium.SeleniumTestCase):

    @classmethod
    def setupClass(cls): 
        cls.job = data_setup.create_job()
        cls.product_before = data_setup.create_product()
        cls.product_after = data_setup.create_product()
        session.flush()

    def setUp(self):
        self.selenium = self.get_selenium()
        self.selenium.start()

    def test_product_ordering(self):
        sel = self.selenium
        self.login()
        sel.open("jobs/%s" % self.job.id)
        products = sel.get_text("//select[@id='job_product']")
        before_pos = products.find(self.product_before.name)
        after_pos = products.find(self.product_after.name)
        self.assert_(before_pos >= 0 and after_pos >= 0 and before_pos < after_pos)

    def tearDown(self):
        self.selenium.stop()
