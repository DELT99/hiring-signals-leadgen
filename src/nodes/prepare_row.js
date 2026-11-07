// Prepare Row
// Single entry point before writing to the sheet (with or without contact lookup).

const lead = $input.first().json;
return [{
  json: {
    ...lead,
    'Contact Name': lead['Contact Name'] || '',
    'Contact Title': lead['Contact Title'] || '',
    'Contact LinkedIn': lead['Contact LinkedIn'] || '',
  },
}];
