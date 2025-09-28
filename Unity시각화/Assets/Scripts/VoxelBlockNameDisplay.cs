using TMPro;
using UnityEngine;

/// 복셀 블록 위에 블록 이름을 표시하는 컴포넌트
/// VoxelBlockVisualizer와 함께 사용됩니다.
public class VoxelBlockNameDisplay : MonoBehaviour
{
    [Header("텍스트 표시 설정")]
    public string blockId = "";
    public float heightOffset = 1.0f; // 블록 위쪽 추가 여백
    public bool enableAutoSize = false; // 자동 폰트 크기 조정 비활성화
    public float fontSize = 24.0f; // 고정 폰트 크기
    public Color textColor = Color.white;
    public bool enableBillboard = false; // 카메라를 향해 회전 (천장을 바라보도록 비활성화)
    public bool lockYRotation = true; // Y축 회전만 허용

    [Header("배경 설정")]
    public bool showBackground = true;
    public Color backgroundColor = new Color(0, 0, 0, 0.7f);
    public Vector2 backgroundPadding = new Vector2(0.5f, 0.2f);

    private TextMeshPro textMesh;
    private GameObject textObj;
    private GameObject backgroundObj;
    private Camera mainCamera;

    void Start()
    {
        mainCamera = Camera.main;
        if (mainCamera == null)
            mainCamera = FindObjectOfType<Camera>();

        CreateTextDisplay();
    }

    void CreateTextDisplay()
    {
        // 블록의 최상단 위치 계산
        Vector3 topPosition = CalculateBlockTopPosition();

        // 텍스트 오브젝트 생성
        textObj = new GameObject($"BlockName_{blockId}");
        textObj.transform.SetParent(transform);
        textObj.transform.position = topPosition;

        // TextMeshPro 컴포넌트 추가
        textMesh = textObj.AddComponent<TextMeshPro>();
        textMesh.text = blockId;
        textMesh.color = textColor;
        textMesh.alignment = TextAlignmentOptions.Center;
        textMesh.verticalAlignment = VerticalAlignmentOptions.Middle;

        // 폰트 크기 및 스타일 설정
        if (enableAutoSize)
        {
            textMesh.enableAutoSizing = true;
            textMesh.fontSizeMin = 0.5f;
            textMesh.fontSizeMax = 10f;
        }
        else
        {
            textMesh.fontSize = fontSize;
        }

        // Bold 스타일 적용
        textMesh.fontStyle = FontStyles.Bold;

        // 텍스트가 천장을 바라보도록 회전 (90도 X축 회전)
        textObj.transform.rotation = Quaternion.Euler(90, 0, 0);

        // 배경 생성
        if (showBackground)
        {
            CreateBackground();
        }

        // 빌보드 효과 추가
        if (enableBillboard)
        {
            BillboardEffect billboard = textObj.AddComponent<BillboardEffect>();
            billboard.lockYRotation = lockYRotation;
        }
    }

    void CreateBackground()
    {
        backgroundObj = new GameObject("Background");
        backgroundObj.transform.SetParent(textObj.transform);
        backgroundObj.transform.localPosition = Vector3.zero;

        // 배경도 텍스트와 같은 방향으로 회전 (천장을 바라봄)
        backgroundObj.transform.localRotation = Quaternion.identity; // 부모와 같은 회전

        // Quad 생성
        MeshRenderer bgRenderer = backgroundObj.AddComponent<MeshRenderer>();
        MeshFilter bgFilter = backgroundObj.AddComponent<MeshFilter>();

        // Quad 메시 생성
        bgFilter.mesh = CreateQuadMesh();

        // 배경 머티리얼 생성
        Material bgMaterial = new Material(Shader.Find("Sprites/Default"));
        bgMaterial.color = backgroundColor;
        bgRenderer.material = bgMaterial;

        // 배경 크기 조정
        UpdateBackgroundSize();
    }

    Mesh CreateQuadMesh()
    {
        Mesh mesh = new Mesh();
        mesh.vertices = new Vector3[]
        {
            new Vector3(-0.5f, -0.5f, 0),
            new Vector3(0.5f, -0.5f, 0),
            new Vector3(-0.5f, 0.5f, 0),
            new Vector3(0.5f, 0.5f, 0)
        };
        mesh.triangles = new int[] { 0, 2, 1, 2, 3, 1 };
        mesh.uv = new Vector2[]
        {
            new Vector2(0, 0),
            new Vector2(1, 0),
            new Vector2(0, 1),
            new Vector2(1, 1)
        };
        mesh.RecalculateNormals();
        return mesh;
    }

    void UpdateBackgroundSize()
    {
        if (backgroundObj == null || textMesh == null) return;

        // 텍스트 크기에 맞춰 배경 크기 조정
        Bounds textBounds = textMesh.bounds;
        float bgWidth = textBounds.size.x + backgroundPadding.x;
        float bgHeight = textBounds.size.y + backgroundPadding.y;

        backgroundObj.transform.localScale = new Vector3(bgWidth, bgHeight, 1);
    }

    Vector3 CalculateBlockTopPosition()
    {
        // 모든 하위 Renderer 찾기 (VoxelBlockVisualizer로 생성된 복셀들)
        Renderer[] renderers = GetComponentsInChildren<Renderer>();

        if (renderers.Length > 0)
        {
            // 모든 복셀의 바운딩 박스를 합쳐서 전체 블록 크기 계산
            Bounds combinedBounds = renderers[0].bounds;

            for (int i = 1; i < renderers.Length; i++)
            {
                combinedBounds.Encapsulate(renderers[i].bounds);
            }

            // 블록 중앙 상단에 위치
            return new Vector3(
                combinedBounds.center.x,
                combinedBounds.max.y + heightOffset,
                combinedBounds.center.z
            );
        }

        // Renderer가 없으면 Transform 위치 기준
        return transform.position + Vector3.up * (2f + heightOffset);
    }

    /// 블록 ID 업데이트
    public void SetBlockId(string newBlockId)
    {
        blockId = newBlockId;
        if (textMesh != null)
        {
            textMesh.text = blockId;
            UpdateBackgroundSize();
        }
    }

    /// 블록 크기 변경시 텍스트 위치 업데이트
    public void RefreshPosition()
    {
        if (textObj != null)
        {
            textObj.transform.position = CalculateBlockTopPosition();
        }
    }

    void Update()
    {
        // 배경 크기 실시간 업데이트 (텍스트 크기가 변할 수 있음)
        if (showBackground && Time.frameCount % 30 == 0) // 30프레임마다 체크
        {
            UpdateBackgroundSize();
        }

        // 천장을 바라보는 방향 유지 (빌보드 효과가 비활성화된 경우)
        if (!enableBillboard)
        {
            textObj.transform.rotation = Quaternion.Euler(90, 0, 0);
        }
    }

#if UNITY_EDITOR
    void OnDrawGizmosSelected()
    {
        // 에디터에서 블록 바운드와 텍스트 위치 시각화
        Renderer[] renderers = GetComponentsInChildren<Renderer>();
        if (renderers.Length > 0)
        {
            Bounds combinedBounds = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++)
            {
                combinedBounds.Encapsulate(renderers[i].bounds);
            }

            Gizmos.color = Color.yellow;
            Gizmos.DrawWireCube(combinedBounds.center, combinedBounds.size);

            Gizmos.color = Color.red;
            Vector3 textPos = new Vector3(
                combinedBounds.center.x,
                combinedBounds.max.y + heightOffset,
                combinedBounds.center.z
            );
            Gizmos.DrawWireSphere(textPos, 0.5f);
        }
    }
#endif
}