'use strict';

// chooseChampion(round): given { mine: [ { power, guile, armour }, ... ],
//                                rivals: [ { power, guile, armour }, ... ] },
// return the index into `mine` of the contender you send into the gauntlet. Your champion fights
// every one of the rival's contenders in turn, and you are judged on how many of those bouts it
// takes.
//
// The Warden decides every bout by one fixed hidden rule. Study the recorded bouts in
// /app/logs.json, each of which names the two contenders and which of them won, work out how the
// Warden decides, and then send in the contender that wins the most.
function chooseChampion(round) {
  throw new Error('chooseChampion not implemented');
}

module.exports = { chooseChampion };
