export interface ReportIndexEntry {
  date: string;
  title: string;
  trendCount: number;
  ownOfficeCount: number;
  windowStart?: string;
  windowEnd?: string;
  generatedAt?: string;
}

export interface ReportItem {
  title: string;
  source: string;
  sourceId?: string;
  category?: string;
  date?: string;
  importance?: number;
  url?: string;
  summaryPoints?: string[];
  analysisPoints?: string[];
  applicationReviewPoints?: string[];
  summaryOnly?: boolean;
}

export interface OwnOfficeItem {
  title: string;
  source?: string;
  date?: string;
  url?: string;
  summaryPoints?: string[];
}

export interface Report {
  metadata: {
    title?: string;
    windowStart?: string;
    windowEnd?: string;
    publishedCount?: number;
    ownOfficePublishedCount?: number;
    analysisModel?: string;
    validationStatus?: string;
  };
  items: ReportItem[];
  ownOfficeItems?: OwnOfficeItem[];
}

export interface NewsItem {
  id: string;
  sourceId?: string;
  source: string;
  title: string;
  date: string;
  url?: string;
}

export interface CoverageArticle {
  title: string;
  publisher: string;
  publishedAt?: string;
  url: string;
  /** "ai"면 구글 검색 연동으로 보완 수집한 기사 */
  via?: string;
}

export interface CoverageItem {
  newsId: string;
  title: string;
  date: string;
  url?: string;
  department?: string | null;
  articleCount: number;
  articles: CoverageArticle[];
}

export interface Coverage {
  generatedAt?: string;
  releaseCount: number;
  coveredCount: number;
  articleCount: number;
  publishers: { name: string; count: number }[];
  departments: {
    name: string;
    releaseCount: number;
    coveredCount: number;
    articleCount: number;
  }[];
  items: CoverageItem[];
}

export type ActiveTab = "reports" | "archive" | "coverage";
