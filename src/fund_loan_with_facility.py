#!/usr/bin/env python3
"""
Your program should consume the input data and attempt to fund each loan with a facility. 
Unfunded loans are ignored by our system -- they will earn no interest, nor will they lose money if they default. 
Your program should be ​streaming,​ meaning it that it should process loans in the order that they are received 
and not use future loans to determine how the current loan should be funded.
Please include instructions on how to run (and build, if necessary) your code. 
Your program should produce two output files: assignments.csv, yields.csv
"""
import csv
import sys
import typing

def get_df(input_file):
    with open(input_file, mode='r') as input_df:
        csvreader = csv.reader(input_df, delimiter=',')
        header = None
        output_df = []
        for row in csvreader:
            if header is None:
                header = row
            else:
                [_, _, _, _] = row
                output_df.append(row)
        return output_df
            
def make_covenants_dict(covenants_input_file):
    covenants_df = get_df(covenants_input_file)
    dict_covenants = dict()
    for [covenant_facility_id, covenant_max_default_likelihood, covenant_bank_id, covenant_banned_state] in covenants_df:
        dict_covenants[covenant_bank_id] = [covenant_facility_id, covenant_max_default_likelihood, covenant_banned_state]
    return dict_covenants

def make_facilities_dict(facilities_input_file):
    facilities_df = get_df(facilities_input_file)
    dict_facilities = dict()
    for [facilities_amount, facilities_interest_rate, facilities_facility_id, facilities_bank_id] in facilities_df:
        dict_facilities[facilities_facility_id] = [facilities_bank_id, facilities_interest_rate, facilities_amount]
    return dict_facilities

def caclulate_yield(default_likelihood: float, loan_int_rate: float, amt: float, facility_int_rate: float) -> float:
    expected_yield = (1 - default_likelihood) * loan_int_rate * amt - (default_likelihood * amt) - (facility_int_rate * amt)
    return expected_yield

def expected_yield_per_facility(facility_id):
    """
    sum all the yields for a facility
    """
    expected_yield_for_facility_id = sum(calculate_yield())
    return expected_yield_for_facility_id

def generate_assignments(loans_input_file = "/." + sys.argv[1] + "/input/loans.csv"):
    def _get_df(input_file):
        with open(input_file, mode='r') as input_df:
            csvreader = csv.reader(input_df, delimiter=',')
            header = None
            output_df = []
            for row in csvreader:
                if header is None:
                    header = row
                else:
                    [_, _, _, _, _] = row
                    output_df.append(row)
        return output_df
    loans_df = _get_df(loans_input_file)
    facilities = make_facilities_dict(facilities_input_file="/." + sys.argv[1] + "/input/facilities.csv")
    covenants = make_covenants_dict(covenants_input_file="./" + sys.argv[1] + "/input/covenants.csv")
    
    for loan_interest_rate, loan_amt, loan_id, loan_default_likelihood, loan_state in loans_df:
        

    return 
