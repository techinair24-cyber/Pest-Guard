function PageIntro({ eyebrow, title, description }) {
  return (
    <section className="page-intro">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      {description && <p className="page-intro-copy">{description}</p>}
    </section>
  )
}

export default PageIntro
