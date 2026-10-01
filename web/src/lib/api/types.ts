// Friendly aliases over the generated OpenAPI types (regenerate with `npm run gen:api`).
import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["UserOut"];
export type TokenResponse = Schemas["TokenResponse"];
export type Organization = Schemas["OrganizationOut"];
export type Invitation = Schemas["InvitationOut"];
export type PublicConfig = Schemas["PublicConfig"];
export type MessageResponse = Schemas["MessageResponse"];

export type Job = Schemas["JobOut"];
export type JobCreate = Schemas["JobCreate"];
export type JobUpdate = Schemas["JobUpdate"];
export type Application = Schemas["ApplicationOut"];
export type CandidateSummary = Schemas["CandidateProfileOut"];
export type CandidateDetail = Schemas["CandidateDetailOut"];
export type CandidateUpdate = Schemas["CandidateProfileUpdate"];
export type SourcedCandidateCreate = Schemas["SourcedCandidateCreate"];
export type CandidateNote = Schemas["CandidateNoteOut"];
export type RecruiterDashboard = Schemas["RecruiterDashboard"];
export type PipelineStage = Schemas["StageOut"];
export type Resume = Schemas["ResumeOut"];
export type DownloadLink = Schemas["DownloadLink"];
export type CandidateMatchList = Schemas["CandidateMatchList"];
export type CandidateMatchItem = Schemas["CandidateMatchItem"];
export type MatchDetail = Schemas["MatchDetail"];
export type MatchFactor = Schemas["FactorOut"];
export type JobMatchItem = Schemas["JobMatchItem"];
export type MatchWeights = Schemas["WeightsOut"];
export type SearchResults = Schemas["SearchResults"];
