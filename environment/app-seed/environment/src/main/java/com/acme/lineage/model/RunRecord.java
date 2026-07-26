package com.acme.lineage.model;

public final class RunRecord {
    public final String runUid;
    public final String releaseAlias;
    public final String legacyAlias;
    public final String stageKind;
    public final String releaseStatus;
    public final String evaluationCohort;
    public final String featureSetHash;
    public final String auc;

    public RunRecord(String runUid, String releaseAlias, String legacyAlias,
                     String stageKind, String releaseStatus, String evaluationCohort,
                     String featureSetHash, String auc) {
        this.runUid = runUid;
        this.releaseAlias = releaseAlias;
        this.legacyAlias = legacyAlias;
        this.stageKind = stageKind;
        this.releaseStatus = releaseStatus;
        this.evaluationCohort = evaluationCohort;
        this.featureSetHash = featureSetHash;
        this.auc = auc;
    }
}
