pyOTPA (Python OpenTripPlanner Analysis tools)
==============================================

A set of tools for assisting with network analysis using OpenTripPlanner :-
tasks such as:-
 * Scripts to help generate OTP Graphs from a set of GTFS files
   (Especially if you want to create many similar graphs with slightly
   different timetables).
 * Scripts to help co-ordinate a set of batch OTP runs, and/or running trips
   on a remote server, and saving details
 * Scripts to then analyse these results in various ways.  

Older notes on some particular scripts
======================================

TrainStations-OD-Matrix:
* Assumes you want to use OTP to calculate routes between all stations in a city's
  (eg Melbourne's) GTFS file.
* makepaths.py :- run this before running the OTP routing operation, as it
  will create all the necessary empty directories first (Otherwise OTP will
  fail with an error message).
* So output directories will be of the form "N\_NAME" - where N is an integer
  number starting at 0, and Name is a name of the station (may include
  spaces).
* make_od_matrix.py : run this after the OTP routing calculation completes,
  and it will create a file called stations_od_matrix.csv - with an OD matrix
  between all the stations, ordered by the Number they are in the file
  structure.

Similarly, TAZs-OD-Matrix:
* Assumes you want to use OTP to calculate routes between all Travel Analysis
  Zones specified for a city.
* It will read the TAZ centroids out of a CSV file called 'taz\_locs.csv'
* makepaths.py :- run this before running the OTP routing operation, as it
  will create all the necessary empty directories first (Otherwise OTP will
  fail with an error message).
* make_od_matrix.csv :- run this after the OTP routing calculation completes,
  it will create a file called tazs_od_matrix.csv .
