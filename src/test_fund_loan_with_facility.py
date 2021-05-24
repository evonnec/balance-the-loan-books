#!/usr/bin/env python3

import pytest
import textwrap
from io import StringIO

import src.fund_loan_with_facility


class TestFundLoanWithFacility:
    def test_self(self):
        sample_input = textwrap.dedent(
            """
            interest_rate,amount,id,default_likelihood,state
            0.15,10552,1,0.02,MO
            0.15,51157,2,0.01,VT
            0.35,74965,3,0.06,AL
            """
        )
        sample_input_file = StringIO(sample_input)
        test_output_file = StringIO()
        src.fund_loan_with_facility.generate_assignments(
            loans_input_file=sample_input,
            assignments_output_file=test_output_file.getvalue()
            )

        output = test_output_file.getvalue()

        expected_output = textwrap.dedent(
            """\
            loan_id,facility_id
            1,1
            2,2
            3,1
            """
        )

        assert output == expected_output


    def test_funded_loan(self):
        pass
    def test_loan_no_facility(self):
        pass
    def test_yield_is_nonnegative(self):
        pass