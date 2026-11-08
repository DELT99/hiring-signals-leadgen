// Build Open Check
// Only for qualified leads on boards that allow it (never LinkedIn): fetch the posting page
// with Firecrawl /scrape so we can confirm it is still accepting applications.

const lead = $input.first().json;
return [{
  json: {
    ...lead,
    scrapeBody: {
      url: lead['Job URL'],
      formats: ['markdown'],
      onlyMainContent: true,
      timeout: 30000,
      maxAge: 86400000,   // accept a cached copy up to 1 day old (cheaper, faster)
    },
  },
}];
