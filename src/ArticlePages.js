import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import BACKEND_BASE from "./config";

const EMPTY_ARTICLE = {
  slug: "",
  title: "",
  date: new Date().toISOString().slice(0, 10),
  description: "",
  tags: [],
  published: false,
  body: "",
};

function isLocalFrontend() {
  return ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function slugify(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 90);
}

function renderInline(text) {
  const nodes = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  String(text || "").replace(pattern, (match, _token, offset) => {
    if (offset > lastIndex) {
      nodes.push(text.slice(lastIndex, offset));
    }
    if (match.startsWith("**")) {
      nodes.push(<strong key={`${offset}-strong`}>{match.slice(2, -2)}</strong>);
    } else if (match.startsWith("*")) {
      nodes.push(<em key={`${offset}-em`}>{match.slice(1, -1)}</em>);
    } else if (match.startsWith("`")) {
      nodes.push(<code key={`${offset}-code`}>{match.slice(1, -1)}</code>);
    } else {
      const linkMatch = match.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      nodes.push(
        <a key={`${offset}-link`} href={linkMatch[2]} target="_blank" rel="noreferrer">
          {linkMatch[1]}
        </a>
      );
    }
    lastIndex = offset + match.length;
    return match;
  });
  if (lastIndex < String(text || "").length) {
    nodes.push(String(text || "").slice(lastIndex));
  }
  return nodes;
}

function MarkdownView({ body }) {
  const blocks = [];
  const lines = String(body || "").split("\n");
  let idx = 0;

  while (idx < lines.length) {
    const line = lines[idx];
    if (!line.trim()) {
      idx += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines = [];
      idx += 1;
      while (idx < lines.length && !lines[idx].startsWith("```")) {
        codeLines.push(lines[idx]);
        idx += 1;
      }
      idx += 1;
      blocks.push(<pre key={`code-${idx}`}><code>{codeLines.join("\n")}</code></pre>);
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const Tag = `h${level + 1}`;
      blocks.push(<Tag key={`heading-${idx}`}>{renderInline(heading[2])}</Tag>);
      idx += 1;
      continue;
    }

    if (line.includes("|") && idx + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[idx + 1])) {
      const tableLines = [line];
      idx += 2;
      while (idx < lines.length && lines[idx].includes("|")) {
        tableLines.push(lines[idx]);
        idx += 1;
      }
      const rows = tableLines.map((tableLine) => tableLine.split("|").map((cell) => cell.trim()).filter(Boolean));
      const [header, ...bodyRows] = rows;
      blocks.push(
        <table key={`table-${idx}`}>
          <thead>
            <tr>{header.map((cell) => <th key={cell}>{renderInline(cell)}</th>)}</tr>
          </thead>
          <tbody>
            {bodyRows.map((row, rowIdx) => (
              <tr key={`row-${rowIdx}`}>
                {row.map((cell, cellIdx) => <td key={`${rowIdx}-${cellIdx}`}>{renderInline(cell)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      );
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (idx < lines.length && /^\s*[-*]\s+/.test(lines[idx])) {
        items.push(lines[idx].replace(/^\s*[-*]\s+/, ""));
        idx += 1;
      }
      blocks.push(
        <ul key={`list-${idx}`}>
          {items.map((item, itemIdx) => <li key={itemIdx}>{renderInline(item)}</li>)}
        </ul>
      );
      continue;
    }

    const paragraph = [line.trim()];
    idx += 1;
    while (idx < lines.length && lines[idx].trim() && !/^(#{1,4})\s+/.test(lines[idx]) && !/^\s*[-*]\s+/.test(lines[idx]) && !lines[idx].startsWith("```")) {
      paragraph.push(lines[idx].trim());
      idx += 1;
    }
    blocks.push(<p key={`paragraph-${idx}`}>{renderInline(paragraph.join(" "))}</p>);
  }

  return <div className="article-body">{blocks}</div>;
}

function ArticleShell({ article }) {
  return (
    <article className="article-shell">
      <header className="article-header">
        <div>
          <p className="home-kicker">{article.published ? "Published" : "Draft"}</p>
          <h1>{article.title || "Untitled article"}</h1>
        </div>
        {article.date && <time>{formatDate(article.date)}</time>}
      </header>
      {article.description && <p className="article-description">{article.description}</p>}
      {Boolean(article.tags?.length) && (
        <div className="article-tags">
          {article.tags.map((tag) => <span key={tag}>{tag}</span>)}
        </div>
      )}
      <MarkdownView body={article.body} />
    </article>
  );
}

export function ArticlesPage() {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${BACKEND_BASE}/articles`)
      .then((res) => res.json())
      .then((data) => setArticles(data.articles || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="articles-page">
      <div className="articles-page-header">
        <div>
          <p className="home-kicker">Articles</p>
          <h2>Notebook</h2>
        </div>
        {isLocalFrontend() && <Link to="/admin/articles" className="home-panel-link">Local editor</Link>}
      </div>
      {loading ? (
        <p className="text-gray-600">Loading articles...</p>
      ) : articles.length ? (
        <div className="article-list">
          {articles.map((article) => (
            <Link className="article-list-item" to={`/articles/${article.slug}`} key={article.slug}>
              <span>{formatDate(article.date)}</span>
              <strong>{article.title}</strong>
              <p>{article.description}</p>
            </Link>
          ))}
        </div>
      ) : (
        <div className="home-panel articles-empty-panel">
          <p className="text-gray-600">No articles published yet.</p>
        </div>
      )}
    </div>
  );
}

export function ArticleDetailPage() {
  const { slug } = useParams();
  const [article, setArticle] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${BACKEND_BASE}/articles/${encodeURIComponent(slug)}`)
      .then((res) => {
        if (!res.ok) throw new Error("Article not found.");
        return res.json();
      })
      .then(setArticle)
      .catch(() => setError("Article not found."));
  }, [slug]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!article) return <p className="text-gray-600">Loading article...</p>;
  return <ArticleShell article={article} />;
}

export function ArticleAdminPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [articles, setArticles] = useState([]);
  const [article, setArticle] = useState(EMPTY_ARTICLE);
  const [status, setStatus] = useState("");

  const tagText = useMemo(() => (article.tags || []).join(", "), [article.tags]);

  useEffect(() => {
    if (!isLocalFrontend()) return;
    fetch(`${BACKEND_BASE}/admin/articles`)
      .then((res) => res.json())
      .then((data) => setArticles(data.articles || []))
      .catch(() => setStatus("The local article editor is only available from localhost."));
  }, []);

  useEffect(() => {
    if (!isLocalFrontend()) return;
    if (!slug) {
      setArticle(EMPTY_ARTICLE);
      return;
    }
    fetch(`${BACKEND_BASE}/admin/articles/${encodeURIComponent(slug)}`)
      .then((res) => {
        if (!res.ok) throw new Error("Article not found.");
        return res.json();
      })
      .then(setArticle)
      .catch(() => setStatus("Article not found."));
  }, [slug]);

  if (!isLocalFrontend()) {
    return (
      <div className="articles-page">
        <div className="home-panel articles-empty-panel">
          <p className="home-kicker">Local editor</p>
          <h2>Unavailable</h2>
          <p className="text-gray-600">
            The article editor is only available when the site is running locally.
          </p>
        </div>
      </div>
    );
  }

  function updateArticle(key, value) {
    setArticle((current) => ({ ...current, [key]: value }));
  }

  async function saveArticle(nextPublished = article.published) {
    const payload = {
      ...article,
      slug: article.slug || slugify(article.title),
      published: nextPublished,
    };
    const res = await fetch(`${BACKEND_BASE}/admin/articles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      setStatus("Article save failed.");
      return;
    }
    const saved = await res.json();
    setArticle(saved);
    setStatus(`${saved.published ? "Published" : "Saved draft"}: ${saved.title}`);
    navigate(`/admin/articles/${saved.slug}`, { replace: true });
    const listRes = await fetch(`${BACKEND_BASE}/admin/articles`);
    const listData = await listRes.json();
    setArticles(listData.articles || []);
  }

  return (
    <div className="article-admin-page">
      <div className="articles-page-header">
        <div>
          <p className="home-kicker">Local editor</p>
          <h2>Article Admin</h2>
        </div>
        <div className="article-admin-actions">
          <Link to="/articles" className="home-panel-link">Public articles</Link>
          <button type="button" className="btn-secondary" onClick={() => navigate("/admin/articles")}>New article</button>
        </div>
      </div>
      {status && <p className="article-admin-status">{status}</p>}
      <div className="article-admin-layout">
        <aside className="article-admin-list">
          {articles.map((item) => (
            <Link to={`/admin/articles/${item.slug}`} key={item.slug} className="article-admin-list-item">
              <strong>{item.title}</strong>
              <span>{item.published ? "Published" : "Draft"}{item.date ? ` | ${item.date}` : ""}</span>
            </Link>
          ))}
        </aside>
        <section className="article-editor-panel">
          <div className="article-editor-fields">
            <label>
              <span>Title</span>
              <input value={article.title} onChange={(e) => updateArticle("title", e.target.value)} />
            </label>
            <label>
              <span>Slug</span>
              <input value={article.slug} onChange={(e) => updateArticle("slug", slugify(e.target.value))} placeholder={slugify(article.title)} />
            </label>
            <label>
              <span>Date</span>
              <input type="date" value={article.date} onChange={(e) => updateArticle("date", e.target.value)} />
            </label>
            <label>
              <span>Tags</span>
              <input value={tagText} onChange={(e) => updateArticle("tags", e.target.value.split(",").map((tag) => tag.trim()).filter(Boolean))} />
            </label>
            <label className="article-editor-description">
              <span>Description</span>
              <input value={article.description} onChange={(e) => updateArticle("description", e.target.value)} />
            </label>
          </div>
          <div className="article-editor-split">
            <label className="article-markdown-editor">
              <span>Markdown</span>
              <textarea value={article.body} onChange={(e) => updateArticle("body", e.target.value)} />
            </label>
            <div className="article-preview-panel">
              <ArticleShell article={article} />
            </div>
          </div>
          <div className="article-admin-save-row">
            <label className="team-profile-toggle">
              <input type="checkbox" checked={article.published} onChange={(e) => updateArticle("published", e.target.checked)} />
              Published
            </label>
            <button type="button" className="btn-secondary" onClick={() => saveArticle(false)}>Save Draft</button>
            <button type="button" className="btn-primary" onClick={() => saveArticle(true)}>Publish</button>
          </div>
        </section>
      </div>
    </div>
  );
}
