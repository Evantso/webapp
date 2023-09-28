"""JSON Error messages returned to client"""


INVALID_API_KEY = {'error': True, 'message': 'Invalid api_key'}
INVALID_EMAIL = {'error': True, 'message': 'Invalid email address'}
INVALID_MOVIE_ID = {'error': True, 'message': 'movie_id is invalid or missing'}
INVALID_MOVIE_ACCESS = {
    'error': True, 'message': 'User does not have access to requested movie.'}
INVALID_COURSE_KEY = {'error': True,
                      'message': 'There is no course for that course key.'}
NO_REMAINING_REGISTRATIONS = {
    'error': True, 'message': 'That course has no remaining registrations. Please contact your faculty member.'}
CALC_RESULTS_PARAM_INVALID = {
    'error': True, 'message': 'All coordinates must be provided (not none) and time elapsed must be greater than zero.'}