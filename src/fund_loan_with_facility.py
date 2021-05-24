#!/usr/bin/env python3

"""
Your program should consume the input data and attempt to fund each loan with a facility. 
  
Unfunded loans are ignored by our system -- they will earn no interest, 
    nor will they lose money if they default.  

Your program should be ​streaming,​ meaning it that it should process loans in the order 
    that they are received, 
and not use future loans to determine how the current loan should be funded.  
  
Please include instructions on how to run (and build, if necessary) your code. 
Your program should produce two output files: assignments.csv, yields.csv
"""

import csv
import sys
import typing
from dataclasses import dataclass

@dataclass
class Facilities:
    facilities_id: int
    facilities_amt: float
    facilities_bank_id: int
    facilities_interest_rate: float
    
    def sort_facilities(self):
        #sorted_facilities_by_interest_rate = sorted(dict_facilities.items(), key=lambda x: (x[1][1], x[1][2]), reverse=True)
        facility_list = list(self._facilities.values())
        facility_list.sort(key=lambda facilities: (-self._facilities_interest_rate, -self._facilities_amt))
        return facility_list

class FacilitiesMinusLoanFunding:
    """
        # facility_id: int,
        # remaining_facility_amount: float,
        # bank_id: int,
        # interest_rate: float
    """
    def __init__(self, loan_amt: float, loan_id: int) -> None:
        self._loan_amt = loan_amt
        self._loan_id = loan_id
        self._facility_id = facilities_id
        self._remaining_facility_amount = facilities_amt
        self._bank_id = facilities_bank_id
        self._interest_rate = facilities_interest_rate
        self._facilities = {}

    def sort_facilities(self):
        #sorted_facilities_by_interest_rate = sorted(dict_facilities.items(), key=lambda x: (x[1][1], x[1][2]), reverse=True)
        facility_list = list(self._facilities.values())
        facility_list.sort(key=lambda facilities: (-facilities.facilities_interest_rate, -facilities.facilities_amt))
        return facility_list
    
    def restrict_facilities(self):
        pass
    
    def assign_loan(self, loan_amt: float, loan_id: int) -> None:
        old_amt = self._remaining_facility_amount
        sort_facilities(self)
             
        while self:
            if self._remaining_facility_amount > self._loan_amt:
                new_amt = Facilities(
                    facility_id=facility_id,
                    facilities_amt=old_amt - loan_amt,
                    facilities_bank_id=bank_id,
                    facilities_interest_rate=interest_rate
                    )
                break
            continue

        with open(assignments_output_file, mode='a') as assignments_output:
            fields = ['loan_id', 'facility_id']
            assignments_output_file = csv.DictWriter(assignments_output, fieldnames=fields)
            if assignments_output_file.readlines() is null:
                assignments_output_file.writeheader()

            line = ",".join(str(self._loan_id), str(self._facility_id))
            assignments_output_file.writerow(line)
            assignments_output.close()

        
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
            
def make_covenants_dict(covenants_input_file, state, default_likelihood):
    """
    make covenants dict of applicable covenants if rules allow us to loan
    """
    covenants_df = get_df(covenants_input_file)
    dict_covenants = dict()
    for [covenant_facility_id, covenant_max_default_likelihood, covenant_bank_id, covenant_banned_state] in covenants_df:
        if covenant_max_default_likelihood == '':
            covenant_max_default_likelihood = 1
        if state != covenant_banned_state and covenant_max_default_likelihood > default_likelihood:
            dict_covenants[covenant_bank_id, covenant_facility_id, covenant_banned_state] = [covenant_max_default_likelihood]
    return dict_covenants

def make_facilities_dict(facilities_input_file):
    """
    make initial facilities dict of all facilities
    load them into the Facilities Class where they will then be the FacilitiesMinusLoanFunding Class
    """
    facilities_df = get_df(facilities_input_file)
    dict_facilities = dict()
    for [facilities_amount, facilities_interest_rate, facilities_facility_id, facilities_bank_id] in facilities_df:
        dict_facilities[facilities_facility_id] = [facilities_bank_id, facilities_interest_rate, facilities_amount]
    return dict_facilities

def calculate_yield(
        default_likelihood: float, 
        loan_int_rate: float, 
        amt: float, 
        facility_int_rate: float
    ) -> float:
    expected_yield = (1 - default_likelihood) * loan_int_rate * amt - (default_likelihood * amt) - (facility_int_rate * amt)
    return expected_yield

def expected_yield_per_facility(facility_id):
    """
    sum all the yields for a facility
    """
    expected_yield_for_facility_id = sum(calculate_yield())
    return expected_yield_for_facility_id

def generate_yields(assignment_file = "./" + sys.argv[1] + "/output/assignments.csv"):
    """
    list all the facility IDs and their total expected
    """
    for facility_id in assignment_file:
        expected_yield_per_facility(facility_id)
        
        csv.writer(csvfile)

def generate_assignments(loans_input_file, assignments_output_file):
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

    dict_of_facilities = make_facilities_dict(facilities_input_file="./" + sys.argv[1] + "/input/facilities.csv")
    sorted_dict_of_facilities = Facilities.sort_facilities(dict_of_facilities)

    # dict_facilities[facilities_facility_id] = [facilities_bank_id, facilities_interest_rate, facilities_amount]
    sorted_dict_of_facilities = Facilities(
        facilities_id=dict_of_facilities.get(dict_of_facilities[key]),
        facilities_amt=dict_of_facilities.get(dict_of_facilities[key][2]),
        facilities_bank_id=dict_of_facilities.get(dict_of_facilities[key][0]),
        facilities_interest_rate=dict_of_facilities.get(dict_of_facilities[key][1]),
            )
    
    # remaining_facilities = FacilitiesMinusLoanFunding(facilities, loan_amt=0)

    for loan_interest_rate, loan_amt, loan_id, loan_default_likelihood, loan_state in loans_df:
        subset_covenants = make_covenants_dict(
            covenants_input_file="./" + sys.argv[1] + "/input/covenants.csv",
            state=loan_state,
            default_likelihood=loan_default_likelihood
            )
        # dict_covenants[covenant_bank_id, covenant_facility_id, covenant_banned_state] = [covenant_max_default_likelihood]
        remaining_facilities = FacilitiesMinusLoanFunding.sort_facilities()
        if remaining_facilities.facility_id in subset_covenants and remaining_facilities.bank_id in subset_covenants:
            FacilitiesMinusLoanFunding.assign_loan(loan_amt=loan_amt,loan_id=loan_id)
        

    return 

if __name__ == "__main__":
    generate_assignments(loans_input_file="./" + sys.argv[1] + "/input/loans.csv", assignments_output_file="./" + sys.argv[1] + "/output/assignments.csv")
