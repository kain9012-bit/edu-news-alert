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

export type ActiveTab = "reports" | "archive";
