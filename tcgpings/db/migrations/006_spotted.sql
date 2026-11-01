-- Member reports of stock seen in stores also tag members whose keywords match.
UPDATE routes SET event_types = array_append(event_types, 'spotted') WHERE member_pings;
