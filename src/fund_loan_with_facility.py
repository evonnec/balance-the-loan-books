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
class Facility:
    facility_id: int
    facility_amt: float
    facility_bank_id: int
    facility_interest_rate: float

@dataclass
class Facilities:
    facilities: typing.List[Facility]
    
    def sort_facilities(self) -> None:
        """
        turns Facilities into a list that's sorted instead of keeping it a dictionary
        """
        #sorted_facilities_by_interest_rate = sorted(dict_facilities.items(), key=lambda x: (x[1][1], x[1][2]), reverse=True)
        self.facilities.sort(key=lambda facility: (-facility.facility_interest_rate, -facility.facility_amt))

class FacilitiesMinusLoanFunding:
    """
        # facility_id: int,
        # remaining_facility_amount: float,
        # bank_id: int,
        # interest_rate: float
    """
    def __init__(
        self,
        facilities: typing.List[Facility],
        loan_amt: float,
    ) -> None:
        self.loan_amt = loan_amt
        self.facilities = facilities

    def sort_facilities(self) -> None:
        self.facilities.sort(key=lambda facility: (-facility.facility_interest_rate, -facility.facility_amt))
    
    def restrict_facilities(self):
        """
        this is taken care of by make_covenants_dict
        """
        pass
    
    def assign_loan(self, loan_amt: float, loan_id: int) -> None:
        old_amt = self._remaining_facility_amount
        self.sort_facilities()
             
        while True:
            if self._remaining_facility_amount > self._loan_amt:
                new_amt = Facilities(
                    facilities_id=self._facility_id,
                    facilities_amt=old_amt - loan_amt,
                    facilities_bank_id=self._bank_id,
                    facilities_interest_rate=self._interest_rate
                    )
                break
            continue
        
        
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
        if state != covenant_banned_state and float(covenant_max_default_likelihood) > float(default_likelihood):
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

def generate_assignments(loans_input_file: str, assignments_output_file: str) -> None:
    """
    as loans come thru, an assignment is made and it writes to file
    """
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

    facility_list = []
    for key, value in dict_of_facilities.items():
        facility = Facility(
            facility_id=int(key),
            facility_amt=float(value[2]),
            facility_bank_id=int(value[0]),
            facility_interest_rate=float(value[1]),
        )
        facility_list.append(facility)
    
    facilities = Facilities(facility_list)
    facilities.sort_facilities()

    # dict_facilities[facilities_facility_id] = [facilities_bank_id, facilities_interest_rate, facilities_amount]

    # remaining_facilities = FacilitiesMinusLoanFunding(facilities, loan_amt=0)
    remaining_facilities = facilities

    for loan_interest_rate, loan_amt, loan_id, loan_default_likelihood, loan_state in loans_df:
        #make available covenants for this particular loan
        subset_covenants = make_covenants_dict(
            covenants_input_file="./" + sys.argv[1] + "/input/covenants.csv",
            state=loan_state,
            default_likelihood=loan_default_likelihood
            )
        
        # what subset_covenants returns: 
        #   dict_covenants[(covenant_bank_id, covenant_facility_id, covenant_banned_state)] = [covenant_max_default_likelihood]
        
        # take a look at the remaining facilities and sort them by interest rate desc, then amt size desc
        remaining_facilities = FacilitiesMinusLoanFunding(
            facilities=remaining_facilities.facilities,
            loan_amt=loan_amt,
        )

        remaining_facilities.sort_facilities()

        # this needs to refactor to work
        for remaining_facility in remaining_facilities.facilities:
            if (
                remaining_facility.facility_id in subset_covenants
                and remaining_facility.bank_id in subset_covenants
            ):
                FacilitiesMinusLoanFunding.assign_loan(loan_amt=loan_amt)
        
            # generate the expected yield
            loan_yield = calculate_yield(default_likelihood=float(loan_default_likelihood), 
                loan_int_rate=float(loan_interest_rate), 
                amt=float(loan_amt), 
                facility_int_rate=float(1)
            )

            # relevant variables assigned to variable to pass
            loan = [loan_id, remaining_facility.facility_id, loan_yield]

            #write out the loan assignment to file    
            write_output(assignments_output_file="./" + sys.argv[1] + "/output/assignments.csv",
                yields_output_file="./" + sys.argv[1] + "/output/yields_initial.csv", loan=loan)


def write_output(assignments_output_file: str, yields_output_file: str, loan: typing.List[typing.Union[str, float]]) -> None:
    [loan_id, facility_id, loan_yield] = loan
    with open(assignments_output_file, mode='r') as assignments_output:
        existing_assignments_lines = assignments_output.readlines()
    with open(assignments_output_file, mode='a') as assignments_output:
        fields = ['loan_id', 'facility_id']
        assignments_output_dict_writer = csv.DictWriter(assignments_output, fieldnames=fields)
        if existing_assignments_lines == []:
            assignments_output_dict_writer.writeheader()
        assignments_output_dict_writer.writerow({"loan_id": str(loan[0]), "facility_id": str(loan[1])})

    
    with open(yields_output_file, mode='r') as yields_output:
        existing_yields_lines = yields_output.readlines()
    with open(yields_output_file, mode='a') as yields_output:
        fields = ['facility_id', 'expected_yield']
        yields_output_dict_writer = csv.DictWriter(yields_output, fieldnames= fields)
        if existing_yields_lines == []:
            yields_output_dict_writer.writeheader()
        yields_output_dict_writer.writerow({"facility_id": str(loan[1]), "expected_yield": str(loan[2])})

def accumulate_yields_per_facility(yields_input_file: str) -> None:
    yields_dict: typing.Dict[str, float] = dict()
    with open(yields_input_file, mode='r') as yields_input:
        csvreader = csv.reader(yields_input, delimiter=',')
        header = None
        for row in csvreader:
            if header is None:
                header = row
            else:
                [facility_id, expected_yield] = row
                expected_yield_float = float(expected_yield)
                if facility_id not in yields_dict:
                    yields_dict[facility_id] = {'total_expected_yield': 0.0}
                yields_dict[facility_id]['total_expected_yield'] += expected_yield_float
                
        output_file = "./" + sys.argv[1] + "/yields.csv"
        with open(output_file, mode='w') as yields_output_file:
            fields = ['facility_id', 'expected_yield']
            output_file_dictwriter = csv.DictWriter(yields_output_file, fieldnames=fields)
            output_file_dictwriter.writeheader()

            for facility_id, total_expected_yield in yields_dict.items():
                pass # TODO
                

if __name__ == "__main__":
    generate_assignments(loans_input_file="./" + sys.argv[1] + "/input/loans.csv", assignments_output_file="./" + sys.argv[1] + "/output/assignments.csv")
    accumulate_yields_per_facility(yields_input_file="./" + sys.argv[1] + "/output/yields_initial.csv")