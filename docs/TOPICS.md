# Topic model v1

Frozen model fit on conferences 1971-04 through 2026-04: 75,409 passages embedded with `BAAI/bge-large-en-v1.5`, clustered with umap+hdbscan(min_cluster_size=100), each passage then assigned to its nearest topic centroid (cosine similarity below 0.763 = no topic).

92 topics; 5 are flagged as boilerplate and hidden from reports. Labels were written by `claude -p` from the terms and five representative passages. Size = training passages assigned.

| ID | Label | Size | Boilerplate | Top terms |
|---|---|---|---|---|
| 75 | Priesthood Holders' Duties | 2836 |  | priesthood, aaronic, aaronic priesthood, quorum, men, power, young, young men, brethren, lord |
| 44 | Faith Through Trials | 2754 |  | faith, us, hope, god, life, lord, things, christ, trials, see |
| 28 | General Exhortations to Members | 2518 | yes | church, us, members, gospel, others, people, need, one, may, world |
| 81 | Tributes to Church Presidents | 2299 |  | president, kimball, president kimball, church, conference, hinckley, monson, prophet, years, twelve |
| 67 | Teaching Children at Home | 2252 |  | children, parents, family, home, teach, families, child, family home, love, teach children |
| 86 | Missionary and Conversion Stories | 2089 |  | mission, missionaries, missionary, church, years, young, said, family, home, baptized |
| 36 | Book of Mormon Stories | 2016 |  | nephi, alma, unto, ye, ne, mormon, lord, god, people, book mormon |
| 73 | Closing Testimonies | 1940 | yes | amen, christ amen, jesus christ, name jesus, name, jesus, christ, testify, may, us |
| 79 | Reading the Book of Mormon | 1642 |  | book, book mormon, mormon, read, christ, bible, joseph, smith, read book, joseph smith |
| 89 | Family Illness and Loss Stories | 1352 |  | mother, would, hospital, family, felt, could, father, years, little, one |
| 46 | Jesus as Son of God | 1338 |  | father, jesus, son, christ, god, jesus christ, john, shall, begotten, name |
| 69 | Addresses to Women and Young Women | 1336 |  | women, young women, sisters, young, daughters, woman, sister, love, dear, women church |
| 31 | Gift of the Holy Ghost | 1314 |  | holy ghost, ghost, holy, spirit, gift, gift holy, truth, receive, us, things |
| 78 | Joseph Smith's First Vision | 1201 |  | joseph, smith, joseph smith, prophet, prophet joseph, vision, son, god, father son, father |
| 40 | Last Days Warnings and Signs | 1167 |  | shall, unto, lord, earth, voice, ye, come, people, upon, coming |
| 38 | Following Christ as Disciples | 1166 |  | follow, christ, jesus, us, savior, jesus christ, come, way, path, unto |
| 87 | Calls to Serve Missions | 1155 |  | missionary, missionaries, mission, serve, young, full time, service, full, young men, missionary service |
| 63 | Repentance and Forgiveness | 1130 |  | repentance, sins, forgive, repent, forgiveness, sin, forgiven, us, lord, mistakes |
| 66 | Eternal Marriage | 1119 |  | marriage, family, wife, husband, married, eternal, children, love, husband wife, divorce |
| 34 | Personal Prayer | 1094 |  | prayer, pray, prayers, father, heavenly father, heavenly, ask, us, help, lord |
| 57 | Plan of Salvation | 1086 |  | plan, eternal, life, earth, father, god, mortal, eternal life, heavenly, heavenly father |
| 80 | Conference Opening and Closing Remarks | 1084 | yes | conference, sisters, general, brothers sisters, brothers, general conference, brethren, messages, great, lord |
| 51 | General Life Observations | 1054 | yes | life, self, one, others, us, good, often, many, things, time |
| 82 | Closing Testimony Formulas | 1028 | yes | jesus christ, prophet, christ, jesus, testify, amen, christ amen, name jesus, witness, name |
| 18 | Church Welfare Program | 996 |  | welfare, services, welfare services, program, church, bishops, welfare program, bishop, ward, employment |
| 64 | Atonement of Jesus Christ | 961 |  | atonement, savior, sins, christ, death, us, jesus, sacrifice, mercy, jesus christ |
| 52 | Relief Society Sisterhood | 941 |  | relief society, relief, society, women, sisters, sister, organization, society sisters, ward, church |
| 35 | Peace Through Christ | 922 |  | peace, world, us, love, christ, let, god, jesus, savior, give unto |
| 41 | Moses, Joshua and Ancient Israel | 773 |  | moses, israel, abraham, lord, egypt, land, joseph, thee, joshua, children israel |
| 54 | Priesthood Keys and Succession | 719 |  | authority, church, presidency, keys, twelve, president, quorum, priesthood, first presidency, president church |
| 61 | Pornography and Immoral Media | 715 |  | pornography, television, sexual, evil, moral, immorality, sex, movies, media, internet |
| 22 | The Two Great Commandments | 691 |  | love, thy, commandment, thou shalt, shalt, shalt love, thou, commandments, great commandment, neighbour |
| 83 | Church Growth in South America | 661 |  | south, america, members, church, missionaries, temple, south america, stake, mission, brazil |
| 19 | Temple Worship and Worthiness | 651 |  | temple, house, temples, ordinances, sacred, covenants, house lord, recommend, holy, lord |
| 45 | Happiness Through Keeping Commandments | 649 |  | happiness, joy, happy, life, plan, commandments, god, plan happiness, us, peace |
| 29 | Seeking Knowledge and Truth | 648 |  | knowledge, truth, study, learning, wisdom, scriptures, seek, god, revelation, things |
| 55 | Satan's Deceptions | 647 |  | satan, devil, evil, us, lucifer, adversary, god, destroy, lies, good |
| 90 | Childhood and Family Stories | 630 |  | mother, dad, car, home, would, could, said, little, boy, one |
| 12 | Light of Christ vs. Darkness | 626 |  | light, darkness, shine, light world, dark, light christ, world, us, christ, shall |
| 42 | Restoration of Priesthood Keys | 620 |  | keys, priesthood, elijah, joseph, smith, joseph smith, oliver, earth, john, prophet |
| 85 | Temple Sealings and Eternal Marriage | 616 |  | temple, sealed, family, married, years, wife, husband, sealing, later, together |
| 47 | Baptism of Jesus and Divine Witnesses | 613 |  | john, unto, jesus, peter, son, baptized, heaven, said, ye, voice |
| 59 | Christ's Suffering in Gethsemane | 607 |  | gethsemane, cross, cup, suffering, jesus, pain, agony, father, suffer, suffered |
| 68 | Motherhood and Women's Roles | 595 |  | mother, women, mothers, woman, children, motherhood, home, role, family, love |
| 60 | Apostasy and Restoration | 593 |  | prophets, earth, gospel, dispensation, revelation, god, amos, restoration, times, apostasy |
| 43 | Pioneer Trek and Sacrifice | 590 |  | valley, pioneers, salt, salt lake, lake, brigham, saints, pioneer, brigham young, wagons |
| 23 | Serving Others | 566 |  | service, serve, others, ye, love, ye service, service god, serving, god, us |
| 48 | Sacrament and Baptismal Covenants | 532 |  | sacrament, partake, baptism, ordinance, always, partake sacrament, always remember, remember, covenant, bread |
| 26 | Pride and Humility | 523 |  | pride, humble, humility, god, man, self, natural, meek, natural man, spirit |
| 65 | Jesus Heals the Sick | 518 |  | healed, thee, sick, jesus, unto, blind, heal, ye, man, saw |
| 32 | Gaining and Bearing Testimony | 506 |  | testimony, testimonies, witness, gospel, truth, know, testimony jesus, jesus, knowledge, christ |
| 14 | Paying Tithing | 498 |  | tithing, pay, tithes, pay tithing, law, paying, lord, tithe, windows heaven, money |
| 8 | Parables of the Savior | 492 |  | ye, fruit, shall, seed, parable, unto, matt, vineyard, harvest, tree |
| 49 | Making and Keeping Covenants | 433 |  | covenant, covenants, keeping, ordinances, keep, path, promises, god, us, keeping covenants |
| 21 | Gospel Teaching and Teachers | 430 |  | teacher, teaching, teach, teachers, gospel, class, students, taught, learning, church |
| 74 | Easter and the Resurrection | 408 |  | easter, resurrection, christ, jesus, jesus christ, sunday, easter sunday, death, savior, season |
| 17 | Humanitarian Aid and Disaster Relief | 406 |  | humanitarian, members, food, church, help, people, many, clothing, supplies, relief |
| 62 | Word of Wisdom and Addiction | 400 |  | drugs, alcohol, tobacco, word wisdom, drug, wisdom, use, health, word, body |
| 20 | Family History and Temple Work | 389 |  | family history, family, ancestors, history, temple, work, names, genealogical, records, ordinances |
| 77 | Temple Announcements and Dedications | 389 |  | temples, temple, dedicated, construction, built, building, new temples, dedication, new, lake temple |
| 88 | Church Growth Statistics | 389 |  | church, missionaries, million, members, stakes, missions, world, number, missionary, years |
| 72 | Joseph and Hyrum's Martyrdom | 379 |  | joseph, smith, joseph smith, hyrum, prophet, prophet joseph, brother, brigham, carthage, church |
| 25 | Unity Among Church Members | 368 |  | unity, one, christ, together, paul, church, god, us, united, one another |
| 27 | Constitution, Freedom, and Citizenship | 367 |  | constitution, nation, land, freedom, government, states, liberty, united states, law, united |
| 33 | Zion and Gathering Israel | 367 |  | zion, shall, gathering, people, israel, lord, house, stakes, nations, earth |
| 30 | Riches and Worldly Wealth | 354 |  | rich, riches, thou, treasure, man, shall, treasures, unto, kingdom, possessions |
| 53 | Honesty and Integrity | 349 |  | integrity, honesty, honest, dishonesty, moral, character, true, lie, virtuous, believe honest |
| 56 | Agency and Freedom to Choose | 333 |  | agency, free, choose, free agency, satan, plan, moral agency, choice, choices, freedom |
| 11 | Shepherds and Lost Sheep | 301 |  | sheep, shepherd, feed, good shepherd, lost, feed sheep, lambs, shepherds, flock, fold |
| 0 | Keeping the Sabbath Holy | 295 |  | sabbath, sabbath day, day, thy, shalt, thou shalt, sunday, thou, keep, holy day |
| 16 | Avoiding Debt, Living Within Means | 292 |  | debt, money, financial, income, economic, pay, get, buy, avoid, credit |
| 6 | Correct Name of the Church | 284 |  | name, church, name church, day saints, latter, latter day, church jesus, saints, christ, christ latter |
| 10 | Peter's Faith on Galilee | 280 |  | peter, sea, simon, nets, thou, disciples, wind, jesus, ship, galilee |
| 24 | Charity, the Pure Love of Christ | 280 |  | charity, love, pure love, love christ, pure, charity pure, endureth, moro, christ, endureth forever |
| 70 | Mary Magdalene at the Empty Tomb | 261 |  | mary, tomb, risen, dead, john, martha, mary magdalene, body, magdalene, sepulchre |
| 15 | Caring for the Poor | 253 |  | poor, needy, poor needy, impart, unto, shall, unto poor, lord, ye, provide saints |
| 58 | Adam, Eve, and the Fall | 242 |  | adam, eve, adam eve, garden, eden, garden eden, fall, moses, god, transgression |
| 50 | Home and Visiting Teaching | 236 |  | home, home teaching, home teachers, teachers, teaching, teacher, home teacher, priesthood, visit, families |
| 7 | King Benjamin's Teachings | 217 |  | benjamin, king benjamin, king, mosiah, ye, people, benjamin taught, god, sins, believe |
| 91 | Outdoor Adventure and Rescue Stories | 214 |  | water, would, could, sheep, top, back, trail, horse, rope, one |
| 4 | Sports Stories and Lessons | 207 |  | team, game, ball, coach, basketball, football, play, players, sports, athletes |
| 76 | Tabernacle and Conference Center Buildings | 205 |  | tabernacle, building, built, temple, conference, structure, hall, temple square, square, years |
| 39 | David, Goliath, and Old Testament Heroes | 201 |  | david, king, samuel, saul, sam, philistine, daniel, goliath, israel, lord |
| 71 | Joseph Smith in Liberty Jail | 182 |  | jail, liberty jail, liberty, joseph, joseph smith, smith, prophet joseph, prophet, thy, prison |
| 13 | Fasting and Fast Offerings | 164 |  | fast, fasting, fast day, poor, thou, thy, law fast, prayer, meals, fast offering |
| 9 | Scouting and Young Men | 151 |  | scout, scouting, scouts, boys, boy, eagle, scoutmaster, youth, boy scouts, men |
| 3 | Patriarchal Blessings | 150 |  | patriarchal, blessing, patriarchal blessing, patriarch, blessings, patriarchal blessings, receive patriarchal, received patriarchal, receive, lineage |
| 5 | Christ's Yoke and Rest | 147 |  | yoke, rest, heavy laden, take yoke, yoke upon, laden, yoke easy, burden, give rest, ye labour |
| 2 | Building on the Rock of Christ | 143 |  | rock, foundation, upon rock, upon, winds, beat upon, built, build, beat, house |
| 37 | Lehi's Tree of Life Vision | 125 |  | tree, lehi, fruit, rod, iron, tree life, rod iron, nephi, iron rod, dream |
| 84 | Flying and Pilot Stories | 114 |  | flight, flying, plane, pilot, pilots, airplane, aircraft, fly, emergency, fighter |
| 1 | Parable of the Ten Virgins | 94 |  | virgins, oil, lamps, bridegroom, foolish, ten virgins, wise, parable, five, ten |
