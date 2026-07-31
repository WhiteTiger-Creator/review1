MATCH (s:CandidateSet)-[:SET_OF]->(f:Framework)
WITH s, f,
  COUNT { MATCH (is0:Argument)-[:RAISES]->(io1:Attack)-[:STRIKES]->(it2:Argument)
    WHERE EXISTS { MATCH (is0)-[:MEMBER]->(s) } AND EXISTS { MATCH (it2)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (io1)<-[:UNDERCUTS]-(uc4:Attack)<-[:RAISES]-(ur3:Argument) WHERE EXISTS { MATCH (ur3)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc4)<-[:UNDERCUTS]-(uc6:Attack)<-[:RAISES]-(ur5:Argument) WHERE EXISTS { MATCH (ur5)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc6)<-[:UNDERCUTS]-(uc8:Attack)<-[:RAISES]-(ur7:Argument) WHERE EXISTS { MATCH (ur7)-[:MEMBER]->(s) } } } } } AS live_internal_attacks,
  COUNT { MATCH (dm9:Argument)-[:MEMBER]->(s)
    WHERE EXISTS { MATCH (da10:Argument)-[:RAISES]->(do11:Attack)-[:STRIKES]->(dm9)
                   WHERE NOT EXISTS { MATCH (do11)<-[:UNDERCUTS]-(uc15:Attack)<-[:RAISES]-(ur14:Argument) WHERE EXISTS { MATCH (ur14)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc15)<-[:UNDERCUTS]-(uc17:Attack)<-[:RAISES]-(ur16:Argument) WHERE EXISTS { MATCH (ur16)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc17)<-[:UNDERCUTS]-(uc19:Attack)<-[:RAISES]-(ur18:Argument) WHERE EXISTS { MATCH (ur18)-[:MEMBER]->(s) } } } } AND NOT EXISTS { MATCH (dd12:Argument)-[:RAISES]->(dc13:Attack)-[:STRIKES]->(da10) WHERE EXISTS { MATCH (dd12)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (dc13)<-[:UNDERCUTS]-(uc21:Attack)<-[:RAISES]-(ur20:Argument) WHERE EXISTS { MATCH (ur20)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc21)<-[:UNDERCUTS]-(uc23:Attack)<-[:RAISES]-(ur22:Argument) WHERE EXISTS { MATCH (ur22)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc23)<-[:UNDERCUTS]-(uc25:Attack)<-[:RAISES]-(ur24:Argument) WHERE EXISTS { MATCH (ur24)-[:MEMBER]->(s) } } } } } } } AS undefended_members,
  COUNT { MATCH (oa26:Argument)-[:IN_FRAMEWORK]->(f)
    WHERE NOT EXISTS { MATCH (oa26)-[:MEMBER]->(s) }
      AND NOT EXISTS { MATCH (om27:Argument)-[:RAISES]->(oo28:Attack)-[:STRIKES]->(oa26)
                        WHERE EXISTS { MATCH (om27)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (oo28)<-[:UNDERCUTS]-(uc30:Attack)<-[:RAISES]-(ur29:Argument) WHERE EXISTS { MATCH (ur29)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc30)<-[:UNDERCUTS]-(uc32:Attack)<-[:RAISES]-(ur31:Argument) WHERE EXISTS { MATCH (ur31)-[:MEMBER]->(s) } AND NOT EXISTS { MATCH (uc32)<-[:UNDERCUTS]-(uc34:Attack)<-[:RAISES]-(ur33:Argument) WHERE EXISTS { MATCH (ur33)-[:MEMBER]->(s) } } } } } } AS unattacked_outsiders
WITH s, f, live_internal_attacks, undefended_members, unattacked_outsiders,
  ((live_internal_attacks + 0) = 0 AND (undefended_members + 0) = 0) AS adm,
  ((live_internal_attacks + 0) = 0 AND (unattacked_outsiders + 0) = 0) AS stb
OPTIONAL MATCH (t:CandidateSet)-[:SET_OF]->(f)
  WHERE t.id <> s.id
    AND NOT EXISTS { MATCH (sa35:Argument)-[:MEMBER]->(s)
                     WHERE NOT EXISTS { MATCH (sa35)-[:MEMBER]->(t) } }
    AND EXISTS { MATCH (sb36:Argument)-[:MEMBER]->(t)
                 WHERE NOT EXISTS { MATCH (sb36)-[:MEMBER]->(s) } }
    AND NOT EXISTS { MATCH (rs37:Argument)-[:RAISES]->(ro38:Attack)-[:STRIKES]->(rt39:Argument)
                     WHERE EXISTS { MATCH (rs37)-[:MEMBER]->(t) } AND EXISTS { MATCH (rt39)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (ro38)<-[:UNDERCUTS]-(uc41:Attack)<-[:RAISES]-(ur40:Argument) WHERE EXISTS { MATCH (ur40)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (uc41)<-[:UNDERCUTS]-(uc43:Attack)<-[:RAISES]-(ur42:Argument) WHERE EXISTS { MATCH (ur42)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (uc43)<-[:UNDERCUTS]-(uc45:Attack)<-[:RAISES]-(ur44:Argument) WHERE EXISTS { MATCH (ur44)-[:MEMBER]->(t) } } } } }
    AND NOT EXISTS { MATCH (dm46:Argument)-[:MEMBER]->(t)
    WHERE EXISTS { MATCH (da47:Argument)-[:RAISES]->(do48:Attack)-[:STRIKES]->(dm46)
                   WHERE NOT EXISTS { MATCH (do48)<-[:UNDERCUTS]-(uc52:Attack)<-[:RAISES]-(ur51:Argument) WHERE EXISTS { MATCH (ur51)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (uc52)<-[:UNDERCUTS]-(uc54:Attack)<-[:RAISES]-(ur53:Argument) WHERE EXISTS { MATCH (ur53)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (uc54)<-[:UNDERCUTS]-(uc56:Attack)<-[:RAISES]-(ur55:Argument) WHERE EXISTS { MATCH (ur55)-[:MEMBER]->(t) } } } } AND NOT EXISTS { MATCH (dd49:Argument)-[:RAISES]->(dc50:Attack)-[:STRIKES]->(da47) WHERE EXISTS { MATCH (dd49)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (dc50)<-[:UNDERCUTS]-(uc58:Attack)<-[:RAISES]-(ur57:Argument) WHERE EXISTS { MATCH (ur57)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (uc58)<-[:UNDERCUTS]-(uc60:Attack)<-[:RAISES]-(ur59:Argument) WHERE EXISTS { MATCH (ur59)-[:MEMBER]->(t) } AND NOT EXISTS { MATCH (uc60)<-[:UNDERCUTS]-(uc62:Attack)<-[:RAISES]-(ur61:Argument) WHERE EXISTS { MATCH (ur61)-[:MEMBER]->(t) } } } } } } }
WITH s, live_internal_attacks, undefended_members, unattacked_outsiders, adm, stb,
     count(t) AS n_super
RETURN s.name AS candidate_set,
       live_internal_attacks AS live_internal_attacks,
       undefended_members AS undefended_members,
       unattacked_outsiders AS unattacked_outsiders,
       adm AS admissible,
       stb AS stable,
       (adm AND (n_super + 0) = 0) AS maximal_admissible
