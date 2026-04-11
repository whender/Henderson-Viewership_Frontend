const TEAM_LOGO_IDS = {
  "Air Force": "2005",
  Akron: "2006",
  Alabama: "333",
  "App State": "2026",
  "Appalachian St.": "2026",
  Arizona: "12",
  "Arizona St.": "9",
  "Arizona State": "9",
  Arkansas: "8",
  "Arkansas St.": "2032",
  "Arkansas State": "2032",
  Army: "349",
  Auburn: "2",
  BYU: "252",
  "Ball St.": "2050",
  "Ball State": "2050",
  Baylor: "239",
  "Boise St.": "68",
  "Boise State": "68",
  "Boston College": "103",
  "Bowling Green": "189",
  Buffalo: "2084",
  California: "25",
  "Central Michigan": "2117",
  Charlotte: "2429",
  Cincinnati: "2132",
  Clemson: "228",
  "Coastal Carolina": "324",
  Colorado: "38",
  "Colorado St.": "36",
  "Colorado State": "36",
  Connecticut: "41",
  Delaware: "48",
  Duke: "150",
  "East Carolina": "151",
  "Eastern Michigan": "2199",
  FAU: "2226",
  FIU: "2229",
  Florida: "57",
  "Florida Atlantic": "2226",
  "Florida International": "2229",
  "Florida St.": "52",
  "Florida State": "52",
  "Fresno St.": "278",
  "Fresno State": "278",
  Georgia: "61",
  "Georgia Southern": "290",
  "Georgia St.": "2247",
  "Georgia State": "2247",
  "Georgia Tech": "59",
  "Hawai'i": "62",
  Hawaii: "62",
  Houston: "248",
  Illinois: "356",
  Indiana: "84",
  Iowa: "2294",
  "Iowa St.": "66",
  "Iowa State": "66",
  Kansas: "2305",
  "Kansas St.": "2306",
  "Kansas State": "2306",
  Kentucky: "96",
  LSU: "99",
  Liberty: "2335",
  Louisiana: "309",
  "Louisiana Monroe": "2433",
  "Louisiana Tech": "2348",
  Louisville: "97",
  Marshall: "276",
  Massachusetts: "113",
  Maryland: "120",
  Memphis: "235",
  Miami: "2390",
  "Miami Ohio": "193",
  Michigan: "130",
  "Michigan St.": "127",
  "Michigan State": "127",
  "Middle Tennessee St.": "2393",
  "Middle Tennessee State": "2393",
  Minnesota: "135",
  Mississippi: "145",
  "Mississippi St.": "344",
  "Mississippi State": "344",
  Missouri: "142",
  "NC State": "152",
  Navy: "2426",
  Nebraska: "158",
  Nevada: "2440",
  "New Mexico": "167",
  "New Mexico St.": "166",
  "New Mexico State": "166",
  "North Carolina": "153",
  "North Carolina St.": "152",
  "North Texas": "249",
  "Northern Illinois": "2459",
  Northwestern: "77",
  "Notre Dame": "87",
  Ohio: "195",
  "Ohio St.": "194",
  "Ohio State": "194",
  Oklahoma: "201",
  "Oklahoma St.": "197",
  "Oklahoma State": "197",
  "Old Dominion": "295",
  "Ole Miss": "145",
  Oregon: "2483",
  "Oregon St.": "204",
  "Oregon State": "204",
  "Penn St.": "213",
  "Penn State": "213",
  Pittsburgh: "221",
  Purdue: "2509",
  Rutgers: "164",
  SMU: "2567",
  "San Diego St.": "21",
  "San Diego State": "21",
  "San Jose St": "23",
  "San Jose St.": "23",
  "San Jose State": "23",
  "Sam Houston": "2534",
  "South Carolina": "2579",
  "South Alabama": "6",
  "South Florida": "58",
  "Southern Miss": "2572",
  Stanford: "24",
  Syracuse: "183",
  TCU: "2628",
  Tennessee: "2633",
  Texas: "251",
  "Texas A&M": "245",
  "Texas St.": "326",
  "Texas State": "326",
  "Texas Tech": "2641",
  Toledo: "2649",
  Troy: "2653",
  Tulane: "2655",
  Tulsa: "202",
  UAB: "5",
  UCF: "2116",
  UCLA: "26",
  UConn: "41",
  UMass: "113",
  USF: "58",
  UNLV: "2439",
  USC: "30",
  UTEP: "2638",
  UTSA: "2636",
  Utah: "254",
  "Utah St.": "328",
  "Utah State": "328",
  Vanderbilt: "238",
  Virginia: "258",
  "Virginia Tech": "259",
  "Wake Forest": "154",
  Washington: "264",
  "Washington St.": "265",
  "Washington State": "265",
  "West Virginia": "277",
  "Western Kentucky": "98",
  "Western Michigan": "2711",
  Wisconsin: "275",
  Wyoming: "2751",
  "Jacksonville St.": "55",
  "Jacksonville State": "55",
  "James Madison": "256",
  "Kennesaw State": "338",
  "Kennesaw St.": "338",
  Temple: "218",
  Rice: "242",
  "Kent St.": "2309",
  "Kent State": "2309",
  "Missouri State": "2623",
};

const TEAM_COLOR_THEMES = {
  "2": { primary: "#0c2340", secondary: "#fdb827" },
  "5": { primary: "#006341", secondary: "#ffb81c" },
  "8": { primary: "#9d2235", secondary: "#ffffff" },
  "9": { primary: "#ffc627", secondary: "#8c1d40" },
  "12": { primary: "#cc0033", secondary: "#003366" },
  "21": { primary: "#a6192e", secondary: "#000000" },
  "24": { primary: "#8c1515", secondary: "#ffffff" },
  "25": { primary: "#041e42", secondary: "#ffc72c" },
  "26": { primary: "#2774ae", secondary: "#ffd100" },
  "30": { primary: "#990000", secondary: "#ffcc00" },
  "36": { primary: "#004c23", secondary: "#c8c372" },
  "38": { primary: "#cfb87c", secondary: "#000000" },
  "41": { primary: "#0f2d52", secondary: "#ffffff" },
  "48": { primary: "#00539f", secondary: "#ffd200" },
  "52": { primary: "#782f40", secondary: "#ceb888" },
  "57": { primary: "#0021a5", secondary: "#fa4616" },
  "58": { primary: "#006747", secondary: "#cfc493" },
  "59": { primary: "#b3a369", secondary: "#ffffff" },
  "61": { primary: "#ba0c2f", secondary: "#000000" },
  "62": { primary: "#005737", secondary: "#000000" },
  "66": { primary: "#ae192d", secondary: "#ffc72a" },
  "68": { primary: "#0033a0", secondary: "#d64309" },
  "77": { primary: "#4e2a84", secondary: "#ffffff" },
  "84": { primary: "#990000", secondary: "#ffffff" },
  "87": { primary: "#062340", secondary: "#c99700" },
  "96": { primary: "#0033a0", secondary: "#ffffff" },
  "97": { primary: "#ad0000", secondary: "#000000" },
  "99": { primary: "#461d7c", secondary: "#fdd023" },
  "103": { primary: "#8c2232", secondary: "#dbcca6" },
  "120": { primary: "#e03a3e", secondary: "#ffd520" },
  "127": { primary: "#173f35", secondary: "#ffffff" },
  "130": { primary: "#00274c", secondary: "#ffcb05" },
  "135": { primary: "#7a0019", secondary: "#ffcc33" },
  "142": { primary: "#000000", secondary: "#f1b82d" },
  "145": { primary: "#13294b", secondary: "#cf142b" },
  "150": { primary: "#003087", secondary: "#ffffff" },
  "151": { primary: "#582c83", secondary: "#ffc72c" },
  "152": { primary: "#cc0000", secondary: "#ffffff" },
  "153": { primary: "#7bafd4", secondary: "#13294b" },
  "154": { primary: "#ceb888", secondary: "#2c2a29" },
  "158": { primary: "#e41c38", secondary: "#ffffff" },
  "164": { primary: "#cc0033", secondary: "#5f6a72" },
  "166": { primary: "#7e141b", secondary: "#231f20" },
  "167": { primary: "#ba0c2f", secondary: "#a7a8aa" },
  "183": { primary: "#f76900", secondary: "#000e54" },
  "189": { primary: "#fd5000", secondary: "#4f2c1d" },
  "193": { primary: "#b61e2e", secondary: "#000000" },
  "194": { primary: "#ba0c2f", secondary: "#a8adb4" },
  "195": { primary: "#00694e", secondary: "#ffffff" },
  "197": { primary: "#fe5c00", secondary: "#000000" },
  "201": { primary: "#841617", secondary: "#fdf9d8" },
  "202": { primary: "#003595", secondary: "#d0b787" },
  "204": { primary: "#dc4405", secondary: "#000000" },
  "213": { primary: "#061440", secondary: "#ffffff" },
  "218": { primary: "#a41e35", secondary: "#ffffff" },
  "221": { primary: "#003594", secondary: "#ffb81c" },
  "228": { primary: "#f56600", secondary: "#522d80" },
  "2294": { primary: "#ffcd00", secondary: "#000000" },
  "2305": { primary: "#0051ba", secondary: "#e8000d" },
  "2306": { primary: "#330a57", secondary: "#e2e3e4" },
  "2309": { primary: "#002664", secondary: "#eaab00" },
  "235": { primary: "#003087", secondary: "#898d8d" },
  "238": { primary: "#000000", secondary: "#866d4b" },
  "239": { primary: "#1b365d", secondary: "#b4975a" },
  "242": { primary: "#862633", secondary: "#ffffff" },
  "245": { primary: "#500000", secondary: "#ffffff" },
  "248": { primary: "#c8102e", secondary: "#ffffff" },
  "249": { primary: "#068f33", secondary: "#ffffff" },
  "251": { primary: "#bf5700", secondary: "#ffffff" },
  "252": { primary: "#0047ba", secondary: "#002e5d" },
  "254": { primary: "#be0000", secondary: "#ffffff" },
  "256": { primary: "#450084", secondary: "#cbb677" },
  "258": { primary: "#f84c1e", secondary: "#232d4b" },
  "259": { primary: "#6a2c3e", secondary: "#cf4520" },
  "264": { primary: "#4b2e83", secondary: "#b7a57a" },
  "265": { primary: "#a60f2d", secondary: "#4d4d4d" },
  "277": { primary: "#eaaa00", secondary: "#002855" },
  "278": { primary: "#b1102b", secondary: "#13284c" },
  "290": { primary: "#041e42", secondary: "#a3aaae" },
  "295": { primary: "#003768", secondary: "#a1d2f1" },
  "309": { primary: "#ce181e", secondary: "#ffffff" },
  "324": { primary: "#006f71", secondary: "#a27752" },
  "326": { primary: "#501214", secondary: "#8c734b" },
  "328": { primary: "#0f2439", secondary: "#ffffff" },
  "333": { primary: "#9e1b32", secondary: "#ffffff" },
  "338": { primary: "#fdbb30", secondary: "#000000" },
  "344": { primary: "#5d1725", secondary: "#c1c6c8" },
  "349": { primary: "#000000", secondary: "#d3bc8d" },
  "356": { primary: "#13294b", secondary: "#e84a27" },
  "2005": { primary: "#003594", secondary: "#ffffff" },
  "2006": { primary: "#041e42", secondary: "#a89968" },
  "2026": { primary: "#000000", secondary: "#ffcd00" },
  "2032": { primary: "#cc092f", secondary: "#000000" },
  "2050": { primary: "#ba0c2f", secondary: "#ffffff" },
  "2084": { primary: "#005bbb", secondary: "#ffffff" },
  "2116": { primary: "#000000", secondary: "#ba9b37" },
  "2117": { primary: "#4c0027", secondary: "#fbab18" },
  "2132": { primary: "#000000", secondary: "#e00122" },
  "2199": { primary: "#006938", secondary: "#ffffff" },
  "2226": { primary: "#003366", secondary: "#cc0000" },
  "2229": { primary: "#091f3f", secondary: "#c3993f" },
  "2247": { primary: "#0039a6", secondary: "#ffffff" },
  "2390": { primary: "#f47321", secondary: "#005030" },
  "2393": { primary: "#0066cc", secondary: "#ffffff" },
  "2426": { primary: "#0c2340", secondary: "#b7c9e2" },
  "2429": { primary: "#005035", secondary: "#a49665" },
  "2433": { primary: "#840029", secondary: "#fdb913" },
  "2439": { primary: "#cf0a2c", secondary: "#b7b7b7" },
  "2440": { primary: "#003366", secondary: "#807f84" },
  "2459": { primary: "#ba0c2f", secondary: "#000000" },
  "2483": { primary: "#154733", secondary: "#fee123" },
  "2509": { primary: "#000000", secondary: "#cfb991" },
  "2534": { primary: "#f56423", secondary: "#ffffff" },
  "2567": { primary: "#0033a0", secondary: "#d71920" },
  "2572": { primary: "#ffc72c", secondary: "#231f20" },
  "2579": { primary: "#73000a", secondary: "#000000" },
  "2628": { primary: "#4d1979", secondary: "#a3a9ac" },
  "2623": { primary: "#5e0009", secondary: "#ffffff" },
  "2633": { primary: "#ff8200", secondary: "#ffffff" },
  "2636": { primary: "#0c2340", secondary: "#f15a22" },
  "2638": { primary: "#ff8200", secondary: "#041e42" },
  "2641": { primary: "#da291c", secondary: "#000000" },
  "2649": { primary: "#15397f", secondary: "#ffcc00" },
  "2653": { primary: "#8a2432", secondary: "#000000" },
  "2655": { primary: "#418fde", secondary: "#53c2b9" },
  "2711": { primary: "#6c4023", secondary: "#ffffff" },
  "275": { primary: "#c5050c", secondary: "#ffffff" },
  "2751": { primary: "#533528", secondary: "#ffc425" },
  "2036": { primary: "#0055a2", secondary: "#e5a823" },
  "2348": { primary: "#003087", secondary: "#cb333b" },
};

const MATCHUP_SEPARATORS = /\s+(?:at|vs\.?|v\.)\s+/i;
const RANKING_PREFIX = /^(?:No\.\s*)?\d+\s+/i;

function cleanTeamName(name) {
  if (!name) {
    return "";
  }

  return String(name)
    .replace(/\s*\([^)]*\)/g, "")
    .replace(RANKING_PREFIX, "")
    .trim();
}

function hashTeamHue(name) {
  return Array.from(String(name || "Team")).reduce(
    (hash, char) => (hash * 31 + char.charCodeAt(0)) % 360,
    0
  );
}

function hslToHex(h, s, l) {
  const saturation = s / 100;
  const lightness = l / 100;
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const segment = h / 60;
  const x = chroma * (1 - Math.abs((segment % 2) - 1));

  let r = 0;
  let g = 0;
  let b = 0;

  if (segment >= 0 && segment < 1) {
    r = chroma;
    g = x;
  } else if (segment < 2) {
    r = x;
    g = chroma;
  } else if (segment < 3) {
    g = chroma;
    b = x;
  } else if (segment < 4) {
    g = x;
    b = chroma;
  } else if (segment < 5) {
    r = x;
    b = chroma;
  } else {
    r = chroma;
    b = x;
  }

  const match = lightness - chroma / 2;
  const toHex = (channel) =>
    Math.round((channel + match) * 255)
      .toString(16)
      .padStart(2, "0");

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

export function getTeamLogoUrl(name) {
  const teamId = TEAM_LOGO_IDS[cleanTeamName(name)];
  return teamId ? `https://a.espncdn.com/i/teamlogos/ncaa/500/${teamId}.png` : null;
}

export function getTeamTheme(name) {
  const cleanName = cleanTeamName(name);
  const teamId = TEAM_LOGO_IDS[cleanName];
  const palette = teamId ? TEAM_COLOR_THEMES[teamId] : null;

  if (palette) {
    return palette;
  }

  const hue = hashTeamHue(cleanName);
  return {
    primary: hslToHex(hue, 62, 34),
    secondary: hslToHex((hue + 28) % 360, 48, 78),
  };
}

export function parseMatchupTeams(matchup) {
  if (!matchup) {
    return [];
  }

  return matchup
    .split(MATCHUP_SEPARATORS)
    .map(cleanTeamName)
    .filter(Boolean)
    .slice(0, 2);
}
