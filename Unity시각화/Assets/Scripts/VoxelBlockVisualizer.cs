using System;
using System.Collections.Generic;
using UnityEngine;
using System.IO;
using UnityEngine.UI;
using TMPro;

/// ship_placer의 복셀 데이터를 직접 시각화하는 컴포넌트
public class VoxelBlockVisualizer : MonoBehaviour
{
    [Header("복셀 시각화 설정")]
    public float voxelSize = 0.5f;  // 복셀 크기 (그리드 해상도)
    public Material voxelMaterial;
    public TextAsset jsonTextAsset;

    [Header("UI 파일 선택")]
    public Button loadFileButton;
    public TMP_Dropdown fileDropdown;
    public TextMeshProUGUI statusText;
    public string configFolderPath = "Assets/Config";

    [Header("디버그")]
    public bool showDebugInfo = true;
    
    private SimpleShipData shipData;
    private Camera mainCamera;
    private List<GameObject> instantiatedBlocks = new List<GameObject>();
    private List<string> availableFiles = new List<string>();
    private string selectedFilePath = "";

    void Start()
    {
        mainCamera = Camera.main;
        if (mainCamera == null)
            mainCamera = FindObjectOfType<Camera>();

        InitializeUI();
        ScanConfigFiles();
        LoadAndVisualize();
    }
    
    private void LoadAndVisualize()
    {
        // JSON 데이터 로드
        shipData = LoadShipData();
        if (shipData == null) return;
        
        Debug.Log($"[VoxelBlockVisualizer] 복셀 시각화 시작 - {shipData.placed_blocks.Count}개 블록");
        
        // 선박 갑판 생성
        CreateShipDeck();
        
        // 복셀 기반 블록들 생성
        CreateVoxelBlocks();
      
    }
    
    private SimpleShipData LoadShipData()
    {
        if (jsonTextAsset == null)
        {
            // JSON TextAsset이 할당되지 않은 경우 조용히 넘어감 (UI로 로드할 예정)
            return null;
        }

        try
        {
            var data = JsonUtility.FromJson<SimpleShipData>(jsonTextAsset.text);
            Debug.Log($"[VoxelBlockVisualizer] JSON 로드 성공: {data.placed_blocks.Count}개 블록");
            return data;
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[VoxelBlockVisualizer] JSON 파싱 오류: {e.Message}");
            return null;
        }
    }
    
    private void CreateShipDeck()
    {
        float shipWidth = shipData.ship_info.dimensions.width;
        float shipHeight = shipData.ship_info.dimensions.height;
        
        GameObject deck = GameObject.CreatePrimitive(PrimitiveType.Quad);
        deck.name = "VoxelShip_Deck";
        deck.transform.position = new Vector3(shipWidth/2f, -0.1f, shipHeight/2f);
        deck.transform.rotation = Quaternion.Euler(90, 0, 0);
        deck.transform.localScale = new Vector3(shipWidth, shipHeight, 1);
        
        // 반투명 갑판 재질
        Material deckMat = new Material(Shader.Find("Standard"));
        deckMat.color = new Color(0.3f, 0.3f, 0.8f, 0.3f);
        deckMat.SetFloat("_Mode", 3);
        deckMat.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
        deckMat.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
        deckMat.SetInt("_ZWrite", 0);
        deckMat.DisableKeyword("_ALPHATEST_ON");
        deckMat.EnableKeyword("_ALPHABLEND_ON");
        deckMat.DisableKeyword("_ALPHAPREMULTIPLY_ON");
        deckMat.renderQueue = 3000;
        deck.GetComponent<Renderer>().material = deckMat;
        
        Debug.Log($"[VoxelBlockVisualizer] 선박 갑판 생성: {shipWidth}m × {shipHeight}m");
    }
    
    private void CreateVoxelBlocks()
    {
        foreach (var blockData in shipData.placed_blocks)
        {
            CreateSingleVoxelBlock(blockData);
        }
    }
    
    private void CreateSingleVoxelBlock(PlacedBlock blockData)
    {
        Debug.Log($"[VoxelBlock] {blockData.id} 복셀 블록 생성 시작");

        // Unity JSON의 복셀 데이터 사용
        if (blockData.voxel_data == null || blockData.voxel_data.positioned_voxels == null)
        {
            Debug.LogWarning($"[VoxelBlock] {blockData.id} - Unity JSON에 복셀 데이터 없음, Fallback 사용");
            CreateFallbackBlock(blockData);
            return;
        }

        // 블록 컨테이너 생성
        GameObject blockContainer = new GameObject($"VoxelBlock_{blockData.id}");

        // 블록 컨테이너는 원점에 위치 (복셀들이 이미 절대 좌표로 배치됨)
        blockContainer.transform.position = Vector3.zero;

        int voxelCount = 0;
        float gridResolution = blockData.voxel_data.grid_resolution;

        // Unity JSON의 positioned_voxels 사용
        foreach (var voxel in blockData.voxel_data.positioned_voxels)
        {
            int x = voxel.x;
            int y = voxel.y;  // 이미 Unity Z 좌표로 변환됨
            var heightInfo = voxel.height_info;

            // 높이 정보에서 실제 높이 계산 (새로운 형식: [min_height, max_height])
            if (heightInfo == null || heightInfo.Count < 2) continue;
            float minHeight = heightInfo[0];  // 최소 높이 (그리드 단위)
            float maxHeight = heightInfo[1];  // 최대 높이 (그리드 단위)
            float actualHeight = (maxHeight - minHeight) * gridResolution;  // 실제 복셀 높이 (미터)

            // 복셀 큐브 생성
            GameObject voxelCube = GameObject.CreatePrimitive(PrimitiveType.Cube);
            voxelCube.name = $"Voxel_{x}_{y}";
            voxelCube.transform.SetParent(blockContainer.transform);

            // BoxCollider 제거 (negative scale 워닝 방지)
            BoxCollider collider = voxelCube.GetComponent<BoxCollider>();
            if (collider != null)
            {
                DestroyImmediate(collider);
            }

            // 복셀 위치 계산 (바닥에서부터 시작)
            float baseElevation = minHeight * gridResolution;  // 바닥 높이 (미터)
            Vector3 voxelPos = new Vector3(
                x * gridResolution,  // Unity X
                baseElevation + actualHeight / 2f,  // Unity Y (바닥 + 높이 중심)
                y * gridResolution   // Unity Z
            );
            voxelCube.transform.position = voxelPos;  // 절대 위치 사용

            // negative scale 방지
            float safeHeight = Mathf.Max(actualHeight, 0.01f);
            voxelCube.transform.localScale = new Vector3(gridResolution, safeHeight, gridResolution);

            // 재질 적용
            if (voxelMaterial != null)
            {
                voxelCube.GetComponent<Renderer>().material = voxelMaterial;
            }
            else
            {
                // 블록 타입별 색상
                Material mat = new Material(Shader.Find("Standard"));
                mat.color = GetBlockTypeColor(blockData.type);
                voxelCube.GetComponent<Renderer>().material = mat;
            }

            voxelCount++;
        }

        // 블록 이름 표시 컴포넌트 추가
        VoxelBlockNameDisplay nameDisplay = blockContainer.AddComponent<VoxelBlockNameDisplay>();
        nameDisplay.SetBlockId(blockData.id);
        nameDisplay.textColor = GetBlockTypeColor(blockData.type);

        // 복셀 데이터는 이미 최적 방향으로 저장되어 있으므로 추가 회전 불필요

        instantiatedBlocks.Add(blockContainer);
        Debug.Log($"[VoxelBlock] {blockData.id} 완료: {voxelCount}개 복셀");
    }
    
    
    
    private Color GetBlockTypeColor(string blockType)
    {
        switch (blockType.ToLower())
        {
            case "trestle": return Color.green;
            case "beam": return Color.blue;
            case "support": return Color.yellow;
            default: return Color.gray;
        }
    }
    
    private void CreateFallbackBlock(PlacedBlock blockData)
    {
        // 복셀 데이터가 없을 때 단순 큐브로 대체
        GameObject fallback = GameObject.CreatePrimitive(PrimitiveType.Cube);
        fallback.name = $"Fallback_{blockData.id}";
        fallback.transform.position = new Vector3(blockData.position.x, 1f, blockData.position.y);
        fallback.transform.localScale = new Vector3(blockData.dimensions.width, 2f, blockData.dimensions.height);

        Material mat = new Material(Shader.Find("Standard"));
        mat.color = Color.red;  // 빨간색으로 표시
        fallback.GetComponent<Renderer>().material = mat;

        // Fallback 블록에도 이름 표시 추가
        VoxelBlockNameDisplay nameDisplay = fallback.AddComponent<VoxelBlockNameDisplay>();
        nameDisplay.SetBlockId(blockData.id);
        nameDisplay.textColor = Color.red;

        instantiatedBlocks.Add(fallback);
        Debug.LogWarning($"[VoxelBlock] {blockData.id} - 복셀 데이터 없음, Fallback 큐브 사용");
    }

    // UI 관련 메서드들
    void InitializeUI()
    {
        // 버튼 이벤트 연결
        if (loadFileButton != null)
            loadFileButton.onClick.AddListener(LoadSelectedFile);

        // 드롭다운 이벤트 연결
        if (fileDropdown != null)
            fileDropdown.onValueChanged.AddListener(OnFileSelected);

        UpdateStatusText("Ready - Please select a file");
    }

    void ScanConfigFiles()
    {
        availableFiles.Clear();

        if (!Directory.Exists(configFolderPath))
        {
            UpdateStatusText($"Config folder not found: {configFolderPath}");
            return;
        }

        string[] jsonFiles = Directory.GetFiles(configFolderPath, "*.json", SearchOption.AllDirectories);
        foreach (string filePath in jsonFiles)
        {
            availableFiles.Add(filePath.Replace("\\", "/"));
        }

        PopulateDropdown();
        UpdateStatusText($"Found {availableFiles.Count} config files");
    }

    void PopulateDropdown()
    {
        if (fileDropdown == null) return;

        fileDropdown.ClearOptions();
        List<TMP_Dropdown.OptionData> options = new List<TMP_Dropdown.OptionData>();
        options.Add(new TMP_Dropdown.OptionData("Select a file..."));

        foreach (string filePath in availableFiles)
        {
            string fileName = Path.GetFileName(filePath);
            options.Add(new TMP_Dropdown.OptionData(fileName));
        }

        fileDropdown.AddOptions(options);
    }

    public void OnFileSelected(int index)
    {
        if (index == 0 || index > availableFiles.Count)
        {
            selectedFilePath = "";
            return;
        }

        selectedFilePath = availableFiles[index - 1];
        UpdateStatusText($"Selected file: {Path.GetFileName(selectedFilePath)}");
    }

    public void LoadSelectedFile()
    {
        if (string.IsNullOrEmpty(selectedFilePath))
        {
            UpdateStatusText("Please select a file first");
            return;
        }

        if (!File.Exists(selectedFilePath))
        {
            UpdateStatusText("Selected file does not exist");
            return;
        }

        // 기존 블록들 정리
        ClearVisualization();

        // 새 파일 로드
        try
        {
            string jsonContent = File.ReadAllText(selectedFilePath);
            TextAsset newAsset = new TextAsset(jsonContent);
            jsonTextAsset = newAsset;

            LoadAndVisualize();
            UpdateStatusText($"Loading complete: {Path.GetFileName(selectedFilePath)}");
        }
        catch (System.Exception e)
        {
            UpdateStatusText($"Loading error: {e.Message}");
        }
    }

    public void ClearVisualization()
    {
        // 이전에 생성된 블록들 삭제
        foreach (GameObject block in instantiatedBlocks)
        {
            if (block != null)
            {
                DestroyImmediate(block);
            }
        }
        instantiatedBlocks.Clear();

        // 갑판 삭제
        GameObject existingDeck = GameObject.Find("VoxelShip_Deck");
        if (existingDeck != null)
        {
            DestroyImmediate(existingDeck);
        }

        UpdateStatusText("Previous visualization cleared");
    }

    void UpdateStatusText(string message)
    {
        if (statusText != null)
        {
            statusText.text = $"Status: {message}";
        }
        Debug.Log($"[VoxelBlockVisualizer] {message}");
    }

    [ContextMenu("시각화 정리")]
    void ClearVisualizationMenu()
    {
        ClearVisualization();
    }
}